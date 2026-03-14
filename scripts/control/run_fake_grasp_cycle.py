#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm
from _safety import check_pose_min_z

prefer_local_pyagxarm(__file__)

VISION_DIR = Path(__file__).resolve().parents[1] / "vision"
if str(VISION_DIR) not in sys.path:
    sys.path.insert(0, str(VISION_DIR))

from _common import (  # type: ignore[no-redef]
    build_pipeline,
    default_model_path,
    detection_rows,
    intrinsics_from_profile,
    put_lines,
    resolve_device,
    resolve_path,
    sample_depth_m,
)

import pyrealsense2 as rs


CLASS_ALIASES = {
    "cell phone": "bottle",
}
DEFAULT_TARGET_LABELS = ["bottle", "cup"]
DEFAULT_TASK_POSES_PATH = Path(__file__).resolve().parents[2] / "config" / "task_poses.yaml"
DEFAULT_DROP_POSES_PATH = Path(__file__).resolve().parents[2] / "config" / "drop_poses.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a fake full pick/place cycle without a hand: home -> work -> target -> standby -> drop -> home."
    )
    parser.add_argument("--model", default=str(default_model_path()), help="Ultralytics model path or name")
    parser.add_argument("--device", default="0", help="Inference device. Use 0 for the first CUDA GPU.")
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU inference for debug use")
    parser.add_argument("--conf", type=float, default=0.15, help="Confidence threshold")
    parser.add_argument("--camera-serial", default="", help="Optional D435 serial number")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--depth-window", type=int, default=2, help="Pixel radius for depth fallback sampling")
    parser.add_argument("--calibration-file", required=True, help="calibration_result.yaml with T_base_camera")
    parser.add_argument("--task-poses-file", default=str(DEFAULT_TASK_POSES_PATH), help="YAML file with home/work/standby poses")
    parser.add_argument("--drop-poses-file", default=str(DEFAULT_DROP_POSES_PATH), help="YAML file with per-class drop XY")
    parser.add_argument("--target-labels", nargs="*", default=DEFAULT_TARGET_LABELS, help="Semantic target labels to keep")
    parser.add_argument("--channel", default="can0", help="SocketCAN channel")
    parser.add_argument("--robot", default="nero", help="Robot model for pyAgxArm")
    parser.add_argument("--speed-percent", type=int, default=10, help="Robot speed percent")
    parser.add_argument("--send-order", default="mode_target_mode", choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"])
    parser.add_argument("--mode-resend", type=int, default=3, help="How many times to resend motion mode")
    parser.add_argument("--hover-height-m", type=float, default=0.20, help="Height above target for pre-grasp hover")
    parser.add_argument(
        "--grasp-z-offset-m",
        type=float,
        default=0.18,
        help="Offset added to target base z for the fake pre-grasp pose; on the current setup, the default 0.18 targets about 10 cm above the object.",
    )
    parser.add_argument("--drop-hover-z-m", type=float, default=0.25, help="Fixed hover z above the drop box")
    parser.add_argument("--drop-z-m", type=float, default=0.15, help="Fixed down/release z over the drop box")
    parser.add_argument(
        "--base-offset-m",
        nargs=3,
        type=float,
        default=[0.0, -0.05, 0.0],
        metavar=("DX", "DY", "DZ"),
        help="Empirical base-frame XYZ correction applied to target hover/pregrasp poses. Current default adds -5 cm on Y.",
    )
    parser.add_argument(
        "--pose-rpy-deg",
        nargs=3,
        type=float,
        default=[90.0, -90.0, 0.0],
        metavar=("ROLL", "PITCH", "YAW"),
        help="Fixed flange orientation used for the fake pick/place cycle.",
    )
    parser.add_argument("--settle-seconds", type=float, default=1.0, help="Wait time after each move.")
    parser.add_argument("--once", action="store_true", help="Exit after one cycle or one dry-run preview.")
    parser.add_argument("--go", action="store_true", help="Actually move the robot. Without this flag, only preview and print.")
    parser.add_argument("--save-json", default="", help="Optional JSONL path for detections and planned poses")
    return parser.parse_args()


def load_yaml(path_str: str) -> tuple[Path, dict[str, Any]]:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"File does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"YAML root must be a mapping: {path}")
    return path, data


def load_base_to_camera(path_str: str) -> tuple[Path, np.ndarray]:
    path, data = load_yaml(path_str)
    try:
        matrix = data["transforms"]["T_base_camera"]["matrix"]
    except Exception as exc:
        raise SystemExit(f"Calibration file is missing transforms.T_base_camera.matrix: {path}") from exc
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.shape != (4, 4):
        raise SystemExit(f"T_base_camera must be 4x4, got {mat.shape} from {path}")
    return path, mat


def load_task_pose(path_str: str, name: str) -> list[float]:
    path, data = load_yaml(path_str)
    task_poses = data.get("task_poses", {})
    if not isinstance(task_poses, dict):
        raise SystemExit(f"'task_poses' must be a mapping: {path}")
    entry = task_poses.get(name)
    if not isinstance(entry, dict) or "pose" not in entry:
        raise SystemExit(f"Task pose '{name}' is missing in {path}")
    pose = entry["pose"]
    if not isinstance(pose, list) or len(pose) != 6:
        raise SystemExit(f"Task pose '{name}' must be a 6-element pose in {path}")
    return [float(v) for v in pose]


def load_drop_xy(path_str: str, label: str) -> list[float]:
    path, data = load_yaml(path_str)
    drop_poses = data.get("drop_poses", {})
    if not isinstance(drop_poses, dict):
        raise SystemExit(f"'drop_poses' must be a mapping: {path}")
    entry = drop_poses.get(label)
    if not isinstance(entry, dict) or "xy" not in entry:
        raise SystemExit(f"Drop XY for '{label}' is missing in {path}")
    xy = entry["xy"]
    if not isinstance(xy, list) or len(xy) != 2:
        raise SystemExit(f"Drop XY for '{label}' must be a 2-element list in {path}")
    return [float(v) for v in xy]


def build_robot(channel: str, robot_name: str):
    from pyAgxArm import AgxArmFactory, create_agx_arm_config

    cfg = create_agx_arm_config(robot=robot_name, comm="can", channel=channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    return robot


def prepare_robot(robot: object, speed_percent: int) -> None:
    if hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
    robot.enable()
    time.sleep(0.2)
    robot.set_speed_percent(speed_percent)


def read_flange_pose(robot: object, timeout_s: float = 2.0) -> list[float] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = robot.get_flange_pose()
        if msg is not None:
            return [float(v) for v in msg.msg]
        time.sleep(0.05)
    return None


def wrap_angle_rad(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def pose_close_enough(
    current_pose: list[float] | None,
    target_pose: list[float],
    *,
    translation_tol_mm: float = 5.0,
    rotation_tol_deg: float = 5.0,
) -> bool:
    if current_pose is None:
        return False
    translation_err_mm = math.sqrt(sum(((current_pose[i] - target_pose[i]) * 1000.0) ** 2 for i in range(3)))
    rotation_err_deg = max(abs(math.degrees(wrap_angle_rad(current_pose[i] - target_pose[i]))) for i in range(3, 6))
    return translation_err_mm <= translation_tol_mm and rotation_err_deg <= rotation_tol_deg


def send_pose(robot: object, target_pose: list[float], send_order: str, mode_resend: int) -> None:
    if not check_pose_min_z(target_pose, "cycle_pose"):
        raise RuntimeError("Blocked by minimum z safety guard.")

    def send_mode_p() -> None:
        for _ in range(max(1, mode_resend)):
            robot.set_motion_mode("p")
            time.sleep(0.02)

    if send_order == "sdk":
        robot.move_p(target_pose)
        return
    if not hasattr(robot, "_deal_move_p_msgs") or not hasattr(robot, "_send_msgs"):
        raise RuntimeError("Selected send_order requires pyAgxArm driver internals.")
    msgs = robot._deal_move_p_msgs(target_pose)
    if send_order == "target_then_mode":
        robot._send_msgs(msgs)
        send_mode_p()
    elif send_order == "mode_then_target":
        send_mode_p()
        robot._send_msgs(msgs)
    elif send_order == "mode_target_mode":
        send_mode_p()
        robot._send_msgs(msgs)
        send_mode_p()
    else:
        raise ValueError(f"Unsupported send_order: {send_order}")


def move_pose(robot: object | None, pose: list[float], execute: bool, label: str, settle_seconds: float, send_order: str, mode_resend: int) -> None:
    print(f"{label}: {pose}")
    if not check_pose_min_z(pose, label):
        raise SystemExit(f"Blocked by minimum z safety guard at {label}.")
    if execute and robot is not None:
        send_pose(robot, pose, send_order, mode_resend)
        time.sleep(max(0.0, settle_seconds))


def choose_target(
    raw_rows: list[dict[str, object]],
    depth_frame: rs.depth_frame,
    intrinsics: rs.intrinsics,
    base_to_camera: np.ndarray,
    *,
    target_labels: list[str],
    depth_window: int,
) -> dict[str, object] | None:
    priority = {label: idx for idx, label in enumerate(target_labels)}
    rows: list[dict[str, object]] = []
    for row in raw_rows:
        original_name = str(row["class_name"])
        target_name = CLASS_ALIASES.get(original_name, original_name)
        row["target_name"] = target_name
        if target_name not in priority:
            continue
        cx, cy = [int(v) for v in row["center_xy"]]
        depth_m = sample_depth_m(depth_frame, cx, cy, depth_window)
        if depth_m <= 0:
            continue
        point_camera = np.asarray(rs.rs2_deproject_pixel_to_point(intrinsics, [cx, cy], depth_m), dtype=np.float64)
        point_base = (base_to_camera[:3, :3] @ point_camera) + base_to_camera[:3, 3]
        row["depth_m"] = float(depth_m)
        row["camera_xyz_m"] = [float(v) for v in point_camera]
        row["base_xyz_m"] = [float(v) for v in point_base]
        rows.append(row)

    rows.sort(
        key=lambda row: (
            priority.get(str(row.get("target_name", row["class_name"])), len(priority)),
            -float(row["confidence"]),
        )
    )
    return rows[0] if rows else None


def build_cycle_poses(best: dict[str, object], args: argparse.Namespace) -> dict[str, list[float]]:
    base = [float(v) for v in best["base_xyz_m"]]
    base_offset = [float(v) for v in args.base_offset_m]
    rpy = [float(np.deg2rad(v)) for v in args.pose_rpy_deg]
    label = str(best.get("target_name", best["class_name"]))
    drop_xy = load_drop_xy(args.drop_poses_file, label)

    target_hover = [
        base[0] + base_offset[0],
        base[1] + base_offset[1],
        base[2] + base_offset[2] + args.hover_height_m,
        *rpy,
    ]
    pregrasp_10cm = [
        base[0] + base_offset[0],
        base[1] + base_offset[1],
        base[2] + base_offset[2] + args.grasp_z_offset_m,
        *rpy,
    ]
    drop_hover = [
        drop_xy[0],
        drop_xy[1],
        args.drop_hover_z_m,
        *rpy,
    ]
    drop_down = [
        drop_xy[0],
        drop_xy[1],
        args.drop_z_m,
        *rpy,
    ]
    return {
        "target_hover": target_hover,
        "pregrasp_10cm": pregrasp_10cm,
        "target_retreat": list(target_hover),
        "drop_hover": drop_hover,
        "drop_down": drop_down,
        "drop_retreat": list(drop_hover),
    }


def annotate_frame(image: np.ndarray, best: dict[str, object] | None, cycle_poses: dict[str, list[float]] | None, args: argparse.Namespace) -> np.ndarray:
    frame = image.copy()
    lines = [
        f"mode={'go' if args.go else 'dry-run'}",
        f"drop_z={args.drop_z_m:.3f}m hover_h={args.hover_height_m:.3f}m",
        "Press g to run one fake cycle, q to quit",
    ]
    if best is not None:
        x1, y1, x2, y2 = [int(v) for v in best["bbox_xyxy"]]
        cx, cy = [int(v) for v in best["center_xy"]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.circle(frame, (cx, cy), 5, (0, 220, 0), -1)
        label_text = str(best["class_name"])
        if best.get("target_name") and best["target_name"] != best["class_name"]:
            label_text = f"{best['class_name']}->{best['target_name']}"
        lines.append(f"target={label_text} conf={float(best['confidence']):.2f}")
        lines.append(
            f"base=({best['base_xyz_m'][0]:.3f}, {best['base_xyz_m'][1]:.3f}, {best['base_xyz_m'][2]:.3f})"
        )
    else:
        lines.append("No valid target")
    if cycle_poses is not None:
        hover = cycle_poses["target_hover"]
        drop = cycle_poses["drop_down"]
        lines.append(f"hover=({hover[0]:.3f}, {hover[1]:.3f}, {hover[2]:.3f})")
        lines.append(
            f"pregrasp=({cycle_poses['pregrasp_10cm'][0]:.3f}, {cycle_poses['pregrasp_10cm'][1]:.3f}, {cycle_poses['pregrasp_10cm'][2]:.3f})"
        )
        lines.append(f"drop=({drop[0]:.3f}, {drop[1]:.3f}, {drop[2]:.3f})")
    return put_lines(frame, lines)


def execute_fake_cycle(robot: object | None, args: argparse.Namespace, cycle_poses: dict[str, list[float]]) -> None:
    home_pose = load_task_pose(args.task_poses_file, "home")
    work_pose = load_task_pose(args.task_poses_file, "work")
    standby_pose = load_task_pose(args.task_poses_file, "standby")

    execute = bool(args.go and robot is not None)
    move_pose(robot, home_pose, execute, "home", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(robot, work_pose, execute, "work", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(robot, cycle_poses["target_hover"], execute, "target_hover", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(
        robot,
        cycle_poses["pregrasp_10cm"],
        execute,
        "pregrasp_10cm",
        args.settle_seconds,
        args.send_order,
        args.mode_resend,
    )
    print("[FAKE GRASP]")
    move_pose(robot, cycle_poses["target_retreat"], execute, "target_retreat", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(robot, standby_pose, execute, "standby", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(robot, cycle_poses["drop_hover"], execute, "drop_hover", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(robot, cycle_poses["drop_down"], execute, "drop_down", args.settle_seconds, args.send_order, args.mode_resend)
    print("[FAKE RELEASE]")
    move_pose(robot, cycle_poses["drop_retreat"], execute, "drop_retreat", args.settle_seconds, args.send_order, args.mode_resend)
    move_pose(robot, home_pose, execute, "return_home", args.settle_seconds, args.send_order, args.mode_resend)


def main() -> int:
    args = parse_args()
    model_path = resolve_path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model file does not exist: {model_path}")

    calibration_path, base_to_camera = load_base_to_camera(args.calibration_file)
    _ = load_task_pose(args.task_poses_file, "home")
    _ = load_task_pose(args.task_poses_file, "work")
    _ = load_task_pose(args.task_poses_file, "standby")
    for label in args.target_labels:
        _ = load_drop_xy(args.drop_poses_file, label)

    device = resolve_device(args.device, args.allow_cpu)
    model = YOLO(str(model_path))
    pipeline, align, profile = build_pipeline(
        camera_serial=args.camera_serial,
        width=args.width,
        height=args.height,
        fps=args.fps,
        enable_depth=True,
    )
    assert align is not None
    intrinsics = intrinsics_from_profile(profile)
    output_path = Path(args.save_json).expanduser().resolve() if args.save_json else None
    output_handle = output_path.open("a", encoding="utf-8") if output_path else None

    robot = None
    home_pose = load_task_pose(args.task_poses_file, "home")
    if args.go:
        robot = build_robot(args.channel, args.robot)
        prepare_robot(robot, args.speed_percent)
        current_pose = read_flange_pose(robot, timeout_s=1.0)
        if pose_close_enough(current_pose, home_pose):
            print("Robot already at home pose; skip startup homing.")
        else:
            print("Robot is not at home pose; moving to home before detection.")
            move_pose(robot, home_pose, True, "startup_home", args.settle_seconds, args.send_order, args.mode_resend)

    window_name = "run_fake_grasp_cycle"
    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned = align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame or not depth_frame:
                continue

            image = np.asanyarray(color_frame.get_data())
            results = model.predict(
                source=image,
                device=device,
                conf=args.conf,
                verbose=False,
                stream=False,
            )
            raw_rows = detection_rows(results[0])
            best = choose_target(
                raw_rows,
                depth_frame,
                intrinsics,
                base_to_camera,
                target_labels=list(args.target_labels),
                depth_window=args.depth_window,
            )
            cycle_poses = build_cycle_poses(best, args) if best is not None else None

            annotated = annotate_frame(image, best, cycle_poses, args)
            cv2.imshow(window_name, annotated)

            if output_handle is not None:
                payload = {
                    "timestamp_unix": time.time(),
                    "best_detection": best,
                    "cycle_poses": cycle_poses,
                    "task_poses_file": str(Path(args.task_poses_file).expanduser().resolve()),
                    "drop_poses_file": str(Path(args.drop_poses_file).expanduser().resolve()),
                }
                output_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                output_handle.flush()

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key != ord("g"):
                continue
            if best is None or cycle_poses is None:
                print("No valid target; fake cycle skipped.")
                continue

            label_text = str(best["class_name"])
            if best.get("target_name") and best["target_name"] != best["class_name"]:
                label_text = f"{best['class_name']}->{best['target_name']}"
            print(f"Selected target: {label_text} conf={float(best['confidence']):.3f}")
            print(f"camera_xyz={best['camera_xyz_m']} base_xyz={best['base_xyz_m']}")
            print(f"Using calibration: {calibration_path}")
            execute_fake_cycle(robot, args, cycle_poses)
            if args.once:
                break
    finally:
        if output_handle is not None:
            output_handle.close()
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
