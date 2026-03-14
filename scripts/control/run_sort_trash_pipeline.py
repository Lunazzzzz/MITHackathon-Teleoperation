#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyrealsense2 as rs
import torch
import yaml
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm
from omnihand_2025_controller import build_omnihand_controller, OmniHandController
from _safety import check_pose_min_z

prefer_local_pyagxarm(__file__)


@dataclass
class TargetPlan:
    label: str
    confidence: float
    pixel_xy: tuple[int, int]
    depth_m: float
    point_camera_m: np.ndarray
    point_base_m: np.ndarray
    approach_pose: list[float]
    grasp_pose: list[float]
    retreat_pose: list[float]
    drop_pose: list[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive skeleton for trash sorting: detection, calibration transform, and robot pick/place."
    )
    parser.add_argument("--config", required=True, help="Pipeline YAML config")
    parser.add_argument("--device", default="0", help="Inference device, e.g. 0 or cpu")
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU inference for debugging")
    parser.add_argument("--go", action="store_true", help="Actually send robot motion commands")
    parser.add_argument("--once", action="store_true", help="Execute at most one pick attempt, then exit")
    parser.add_argument("--no-display", action="store_true", help="Run without an OpenCV preview window")
    parser.add_argument("--self-test", action="store_true", help="Skip camera/robot and run one blank-frame inference")
    parser.add_argument("--self-test-output", default="", help="Optional path to save the self-test annotated image")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"YAML root must be a mapping: {path}")
    return data


def resolve_path(path_str: str, config_path: Path, repo_root: Path) -> Path:
    path = Path(path_str).expanduser()
    if path.is_absolute():
        return path.resolve()
    config_relative = (config_path.parent / path).resolve()
    if config_relative.exists():
        return config_relative
    return (repo_root / path).resolve()


def resolve_device(device: str, allow_cpu: bool) -> str:
    if device == "cpu":
        if not allow_cpu:
            raise SystemExit("CPU inference requested but --allow-cpu was not provided")
        return "cpu"
    if torch.cuda.is_available():
        return device
    if allow_cpu:
        print("Warning: CUDA is unavailable; falling back to CPU inference.")
        return "cpu"
    raise SystemExit("CUDA is unavailable. Re-run with --allow-cpu for slow debug inference.")


def build_camera(camera_cfg: dict[str, Any]) -> tuple[rs.pipeline, rs.align, rs.pipeline_profile, rs.intrinsics]:
    pipeline = rs.pipeline()
    config = rs.config()
    serial = str(camera_cfg.get("serial", "")).strip()
    if serial:
        config.enable_device(serial)
    width = int(camera_cfg.get("width", 1280))
    height = int(camera_cfg.get("height", 720))
    fps = int(camera_cfg.get("fps", 30))
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
    config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
    profile = pipeline.start(config)
    time.sleep(1.0)
    align = rs.align(rs.stream.color)
    intrinsics = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
    return pipeline, align, profile, intrinsics


def sample_depth_m(depth_frame: rs.depth_frame, u: int, v: int, radius: int) -> float:
    height = depth_frame.get_height()
    width = depth_frame.get_width()
    best = 0.0
    for du in range(-radius, radius + 1):
        for dv in range(-radius, radius + 1):
            uu = min(max(u + du, 0), width - 1)
            vv = min(max(v + dv, 0), height - 1)
            depth = float(depth_frame.get_distance(uu, vv))
            if depth > 0:
                return depth
            best = max(best, depth)
    return best


def choose_target(
    result: Any,
    depth_frame: rs.depth_frame,
    intrinsics: rs.intrinsics,
    base_to_camera: np.ndarray,
    config: dict[str, Any],
) -> TargetPlan | None:
    classes_cfg = config.get("classes", {})
    workflow_cfg = config.get("workflow", {})
    robot_cfg = config.get("robot", {})
    target_labels = set(workflow_cfg.get("target_labels", []))
    depth_window = int(config.get("camera", {}).get("depth_window_px", 2))
    fixed_rpy = [float(v) for v in robot_cfg.get("pose_rpy_rad", [3.141593, 0.0, 0.0])]

    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None

    names = result.names
    best_plan = None
    best_score = -1.0
    for box in boxes:
        cls_idx = int(box.cls[0])
        label = str(names[cls_idx])
        if target_labels and label not in target_labels:
            continue
        class_cfg = classes_cfg.get(label)
        if not isinstance(class_cfg, dict) or "drop_pose" not in class_cfg:
            continue

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        u = int((x1 + x2) * 0.5)
        v = int((y1 + y2) * 0.5)
        depth_m = sample_depth_m(depth_frame, u, v, depth_window)
        if depth_m <= 0:
            continue

        point_camera = np.asarray(rs.rs2_deproject_pixel_to_point(intrinsics, [u, v], depth_m), dtype=np.float64)
        point_base = base_to_camera[:3, :3] @ point_camera + base_to_camera[:3, 3]
        approach_offset = float(robot_cfg.get("approach_offset_m", 0.10))
        retreat_offset = float(robot_cfg.get("retreat_offset_m", approach_offset))
        grasp_z_offset = float(robot_cfg.get("grasp_z_offset_m", 0.015))

        grasp_pose = [
            float(point_base[0]),
            float(point_base[1]),
            float(point_base[2] + grasp_z_offset),
            *fixed_rpy,
        ]
        approach_pose = grasp_pose.copy()
        approach_pose[2] += approach_offset
        retreat_pose = grasp_pose.copy()
        retreat_pose[2] += retreat_offset
        drop_pose = [float(v) for v in class_cfg["drop_pose"]]

        plan = TargetPlan(
            label=label,
            confidence=conf,
            pixel_xy=(u, v),
            depth_m=depth_m,
            point_camera_m=point_camera,
            point_base_m=point_base,
            approach_pose=approach_pose,
            grasp_pose=grasp_pose,
            retreat_pose=retreat_pose,
            drop_pose=drop_pose,
        )
        if conf > best_score:
            best_score = conf
            best_plan = plan
    return best_plan


def load_calibration(path: Path) -> np.ndarray:
    calibration = load_yaml(path)
    try:
        matrix = calibration["transforms"]["T_base_camera"]["matrix"]
    except KeyError as exc:
        raise SystemExit(f"Calibration file is missing T_base_camera: {path}") from exc
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.shape != (4, 4):
        raise SystemExit(f"T_base_camera must be 4x4, got {mat.shape} from {path}")
    return mat


def build_robot(robot_cfg: dict[str, Any]) -> Any:
    from pyAgxArm import AgxArmFactory, create_agx_arm_config

    cfg = create_agx_arm_config(
        robot=str(robot_cfg.get("model", "nero")),
        comm="can",
        channel=str(robot_cfg.get("channel", "can0")),
        interface="socketcan",
    )
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    return robot


def prepare_robot(robot: Any, robot_cfg: dict[str, Any]) -> None:
    if hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
    robot.enable()
    time.sleep(0.2)
    robot.set_speed_percent(int(robot_cfg.get("speed_percent", 20)))


def move_pose(robot: Any, pose: list[float], execute: bool, label: str) -> None:
    print(f"{label}: {pose}")
    if not check_pose_min_z(pose, label):
        raise SystemExit(f"Blocked by minimum z safety guard at {label}.")
    if execute:
        robot.move_p(pose)
        time.sleep(0.3)


def open_hand(hand: OmniHandController | None, execute: bool) -> None:
    if hand is None:
        message = "OmniHand open skipped (hand disabled or --go not set)"
        print(message)
        time.sleep(0.1)
        return
    if not execute:
        print("OmniHand open skipped (dry-run)")
        time.sleep(0.1)
        return
    hand.open()


def close_hand(hand: OmniHandController | None, execute: bool) -> None:
    if hand is None:
        message = "OmniHand close skipped (hand disabled or --go not set)"
        print(message)
        time.sleep(0.1)
        return
    if not execute:
        print("OmniHand close skipped (dry-run)")
        time.sleep(0.1)
        return
    hand.close()


def execute_plan(
    plan: TargetPlan,
    robot: Any,
    hand: OmniHandController | None,
    config: dict[str, Any],
    execute: bool,
) -> None:
    robot_cfg = config.get("robot", {})
    home_pose = robot_cfg.get("home_pose")
    if home_pose:
        move_pose(robot, [float(v) for v in home_pose], execute, "home_pose")
    open_hand(hand, execute)
    move_pose(robot, plan.approach_pose, execute, "approach_pose")
    move_pose(robot, plan.grasp_pose, execute, "grasp_pose")
    close_hand(hand, execute)
    move_pose(robot, plan.retreat_pose, execute, "retreat_pose")
    move_pose(robot, plan.drop_pose, execute, f"drop_pose[{plan.label}]")
    open_hand(hand, execute)
    if home_pose:
        move_pose(robot, [float(v) for v in home_pose], execute, "return_home_pose")


def print_plan(plan: TargetPlan) -> None:
    print(f"Selected target: {plan.label} conf={plan.confidence:.3f}")
    print(f"Pixel center: {plan.pixel_xy}, depth={plan.depth_m:.4f} m")
    print(f"Camera point (m): {plan.point_camera_m.tolist()}")
    print(f"Base point (m): {plan.point_base_m.tolist()}")
    print(f"Approach pose: {plan.approach_pose}")
    print(f"Grasp pose: {plan.grasp_pose}")
    print(f"Retreat pose: {plan.retreat_pose}")
    print(f"Drop pose: {plan.drop_pose}")


def annotate_frame(image: np.ndarray, plan: TargetPlan | None, go_enabled: bool) -> np.ndarray:
    frame = image.copy()
    if plan is None:
        cv2.putText(frame, "No valid target", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return frame

    x, y = plan.pixel_xy
    cv2.circle(frame, (x, y), 6, (0, 255, 0), -1)
    lines = [
        f"target={plan.label} conf={plan.confidence:.2f} depth={plan.depth_m:.3f}m",
        f"base=({plan.point_base_m[0]:.3f}, {plan.point_base_m[1]:.3f}, {plan.point_base_m[2]:.3f})",
        "press g to execute" if go_enabled else "dry-run only; add --go to move robot",
    ]
    for idx, line in enumerate(lines):
        cv2.putText(frame, line, (20, 30 + idx * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return frame


def run_self_test(
    args: argparse.Namespace,
    config: dict[str, Any],
    model: YOLO,
    base_to_camera: np.ndarray,
    device: str,
    repo_root: Path,
) -> int:
    camera_cfg = config.get("camera", {})
    width = int(camera_cfg.get("width", 1280))
    height = int(camera_cfg.get("height", 720))
    image = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(image, "sort_trash self-test", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    results = model.predict(
        source=image,
        device=device,
        conf=float(config.get("workflow", {}).get("detection_conf", 0.25)),
        verbose=False,
        stream=False,
    )
    result = results[0]
    plan = None
    annotated = annotate_frame(image, plan, args.go)
    output_path = None
    if args.self_test_output:
        output_path = Path(args.self_test_output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), annotated)
    print("Self-test complete.")
    print(f"Model names count: {len(result.names)}")
    print(f"Detected boxes on blank frame: {0 if result.boxes is None else len(result.boxes)}")
    print(f"T_base_camera[0:3,3]: {base_to_camera[:3, 3].tolist()}")
    if output_path is not None:
        try:
            rel = output_path.relative_to(repo_root)
            print(f"Annotated image written to: {rel}")
        except ValueError:
            print(f"Annotated image written to: {output_path}")
    return 0


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_yaml(config_path)
    repo_root = Path(__file__).resolve().parents[2]
    model_path = resolve_path(str(config["model"]), config_path, repo_root)
    calibration_path = resolve_path(str(config["calibration_file"]), config_path, repo_root)
    if not model_path.exists():
        raise SystemExit(f"Model file does not exist: {model_path}")
    if not calibration_path.exists():
        raise SystemExit(f"Calibration file does not exist: {calibration_path}")

    device = resolve_device(args.device, args.allow_cpu)
    base_to_camera = load_calibration(calibration_path)
    model = YOLO(str(model_path))
    if args.self_test:
        return run_self_test(args, config, model, base_to_camera, device, repo_root)

    robot = None
    robot_cfg = config.get("robot", {})
    if args.go and bool(robot_cfg.get("enabled", True)):
        robot = build_robot(robot_cfg)
        prepare_robot(robot, robot_cfg)
    hand = build_omnihand_controller(config.get("hand", {}), execute=args.go)

    pipeline, align, _profile, intrinsics = build_camera(config.get("camera", {}))
    window_name = "run_sort_trash_pipeline"
    auto_pick = bool(config.get("workflow", {}).get("auto_pick", False))
    executed_once = False

    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)
            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()
            if not color_frame or not depth_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())
            results = model.predict(
                source=color_image,
                device=device,
                conf=float(config.get("workflow", {}).get("detection_conf", 0.25)),
                verbose=False,
                stream=False,
            )
            plan = choose_target(results[0], depth_frame, intrinsics, base_to_camera, config)

            if not args.no_display:
                annotated = annotate_frame(color_image, plan, args.go)
                cv2.imshow(window_name, annotated)

            should_execute = plan is not None and args.once and (auto_pick or args.no_display)
            key = cv2.waitKey(1) & 0xFF if not args.no_display else 255
            if key == ord("q"):
                break
            if key == ord("g") and plan is not None:
                should_execute = True

            if not should_execute:
                continue
            print_plan(plan)
            if robot is not None:
                execute_plan(plan, robot, hand, config, args.go)
            else:
                print("Dry run: robot motion was not executed.")
            executed_once = True
            if args.once:
                break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

    return 0 if executed_once or not args.once else 1


if __name__ == "__main__":
    sys.exit(main())
