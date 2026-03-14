#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyrealsense2 as rs
import yaml
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm
from omnihand_2025_controller import build_omnihand_controller, OmniHandController

prefer_local_pyagxarm(__file__)

VISION_DIR = Path(__file__).resolve().parents[1] / "vision"
if str(VISION_DIR) not in sys.path:
    sys.path.insert(0, str(VISION_DIR))

from _common import (  # type: ignore[no-redef]
    build_pipeline,
    detection_rows,
    intrinsics_from_profile,
    put_lines,
    resolve_device,
    sample_depth_m,
)

from hover_detected_target import build_robot, prepare_robot, send_hover_pose


@dataclass
class BottleTemplatePlan:
    label: str
    confidence: float
    pixel_xy: tuple[int, int]
    depth_m: float
    point_camera_m: np.ndarray
    point_base_m: np.ndarray
    grasp_center_m: np.ndarray
    approach_dir_m: np.ndarray
    hover_pose: list[float]
    pregrasp_pose: list[float]
    ingress_pose: list[float]
    lift_pose: list[float]
    retreat_pose: list[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Template pick helper for lying bottles: hover, side-top pregrasp, ingress, close, and lift."
    )
    parser.add_argument("--config", required=True, help="Pipeline YAML config")
    parser.add_argument("--device", default="0", help="Inference device, e.g. 0 or cpu")
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU inference for debugging")
    parser.add_argument("--go", action="store_true", help="Actually send robot and hand commands")
    parser.add_argument("--once", action="store_true", help="Execute one pick template automatically, then exit")
    parser.add_argument("--no-display", action="store_true", help="Run without an OpenCV preview window")
    parser.add_argument("--target-labels", nargs="*", default=["bottle"], help="Class labels to treat as lying-cylinder targets")
    parser.add_argument(
        "--pose-rpy-deg",
        nargs=3,
        type=float,
        default=[90.0, -25.0, 0.0],
        metavar=("ROLL", "PITCH", "YAW"),
        help="Fixed end-effector orientation for the side-top bottle template",
    )
    parser.add_argument(
        "--approach-axis",
        choices=["x", "-x", "y", "-y", "z", "-z"],
        default="x",
        help="Tool-frame axis used as the template approach direction",
    )
    parser.add_argument("--hover-height-m", type=float, default=0.18, help="Height above the corrected grasp center")
    parser.add_argument("--surface-to-center-z-offset-m", type=float, default=-0.03, help="Adjust detected surface point to bottle center height")
    parser.add_argument("--grasp-offset-xyz-m", nargs=3, type=float, default=[0.0, 0.0, 0.0], metavar=("DX", "DY", "DZ"), help="Additional base-frame offset applied to the corrected grasp center")
    parser.add_argument("--pregrasp-backoff-m", type=float, default=0.08, help="Back off from the grasp center along the approach direction")
    parser.add_argument("--pregrasp-lift-m", type=float, default=0.05, help="Extra Z lift applied at pregrasp")
    parser.add_argument("--ingress-backoff-m", type=float, default=0.015, help="Residual backoff before closing the hand")
    parser.add_argument("--ingress-z-offset-m", type=float, default=0.0, help="Extra Z offset applied at ingress")
    parser.add_argument("--lift-m", type=float, default=0.08, help="Post-close vertical lift")
    parser.add_argument("--retreat-backoff-m", type=float, default=0.05, help="Back off after lifting to reduce table collisions")
    parser.add_argument("--hand-close-settle-s", type=float, default=0.5, help="Wait after closing before lifting")
    parser.add_argument(
        "--send-order",
        default="mode_target_mode",
        choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"],
        help="How to send Cartesian target poses to the robot",
    )
    parser.add_argument("--mode-resend", type=int, default=3, help="How many times to resend motion mode around pose sends")
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


def load_base_to_camera(path: Path) -> np.ndarray:
    data = load_yaml(path)
    try:
        matrix = data["transforms"]["T_base_camera"]["matrix"]
    except Exception as exc:
        raise SystemExit(f"Calibration file is missing transforms.T_base_camera.matrix: {path}") from exc
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.shape != (4, 4):
        raise SystemExit(f"T_base_camera must be 4x4, got {mat.shape} from {path}")
    return mat


def rpy_to_rot(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=np.float64,
    )


def axis_from_rotation(rotation: np.ndarray, axis_name: str) -> np.ndarray:
    index_map = {"x": 0, "y": 1, "z": 2}
    sign = -1.0 if axis_name.startswith("-") else 1.0
    axis = axis_name[-1]
    vec = rotation[:, index_map[axis]].astype(np.float64)
    norm = np.linalg.norm(vec)
    if norm <= 0:
        raise SystemExit(f"Invalid approach axis derived from pose: {axis_name}")
    return sign * (vec / norm)


def pose_from_xyz_rpy(xyz: np.ndarray, rpy: list[float]) -> list[float]:
    return [float(xyz[0]), float(xyz[1]), float(xyz[2]), *[float(v) for v in rpy]]


def choose_target(
    result: Any,
    depth_frame: rs.depth_frame,
    intrinsics: rs.intrinsics,
    base_to_camera: np.ndarray,
    target_labels: list[str],
) -> dict[str, object] | None:
    label_set = set(target_labels)
    rows: list[dict[str, object]] = []
    for row in detection_rows(result):
        if label_set and str(row["class_name"]) not in label_set:
            continue
        cx, cy = [int(v) for v in row["center_xy"]]
        depth_m = sample_depth_m(depth_frame, cx, cy, 2)
        if depth_m <= 0:
            continue
        point_camera = np.asarray(rs.rs2_deproject_pixel_to_point(intrinsics, [cx, cy], depth_m), dtype=np.float64)
        point_base = (base_to_camera[:3, :3] @ point_camera) + base_to_camera[:3, 3]
        row["depth_m"] = float(depth_m)
        row["camera_xyz_m"] = [float(v) for v in point_camera]
        row["base_xyz_m"] = [float(v) for v in point_base]
        rows.append(row)
    rows.sort(key=lambda row: float(row["confidence"]), reverse=True)
    return rows[0] if rows else None


def build_plan(best: dict[str, object], args: argparse.Namespace) -> BottleTemplatePlan:
    point_camera = np.asarray(best["camera_xyz_m"], dtype=np.float64)
    point_base = np.asarray(best["base_xyz_m"], dtype=np.float64)
    pose_rpy_rad = [float(np.deg2rad(v)) for v in args.pose_rpy_deg]
    rotation = rpy_to_rot(*pose_rpy_rad)
    approach_dir = axis_from_rotation(rotation, args.approach_axis)

    grasp_center = point_base.copy()
    grasp_center[2] += float(args.surface_to_center_z_offset_m)
    grasp_center += np.asarray([float(v) for v in args.grasp_offset_xyz_m], dtype=np.float64)

    hover_xyz = grasp_center.copy()
    hover_xyz[2] += float(args.hover_height_m)

    pregrasp_xyz = grasp_center - approach_dir * float(args.pregrasp_backoff_m)
    pregrasp_xyz[2] += float(args.pregrasp_lift_m)

    ingress_xyz = grasp_center - approach_dir * float(args.ingress_backoff_m)
    ingress_xyz[2] += float(args.ingress_z_offset_m)

    lift_xyz = ingress_xyz.copy()
    lift_xyz[2] += float(args.lift_m)

    retreat_xyz = lift_xyz - approach_dir * float(args.retreat_backoff_m)

    return BottleTemplatePlan(
        label=str(best["class_name"]),
        confidence=float(best["confidence"]),
        pixel_xy=(int(best["center_xy"][0]), int(best["center_xy"][1])),
        depth_m=float(best["depth_m"]),
        point_camera_m=point_camera,
        point_base_m=point_base,
        grasp_center_m=grasp_center,
        approach_dir_m=approach_dir,
        hover_pose=pose_from_xyz_rpy(hover_xyz, pose_rpy_rad),
        pregrasp_pose=pose_from_xyz_rpy(pregrasp_xyz, pose_rpy_rad),
        ingress_pose=pose_from_xyz_rpy(ingress_xyz, pose_rpy_rad),
        lift_pose=pose_from_xyz_rpy(lift_xyz, pose_rpy_rad),
        retreat_pose=pose_from_xyz_rpy(retreat_xyz, pose_rpy_rad),
    )


def draw_target_box(image: np.ndarray, best: dict[str, object]) -> None:
    x1, y1, x2, y2 = [int(v) for v in best["bbox_xyxy"]]
    cx, cy = [int(v) for v in best["center_xy"]]
    color = (0, 220, 0)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
    cv2.circle(image, (cx, cy), 5, color, -1)
    cv2.drawMarker(image, (cx, cy), color, cv2.MARKER_CROSS, 18, 2)


def overlay_lines(plan: BottleTemplatePlan | None, go: bool) -> list[str]:
    lines = [
        "Lying Bottle Pick Template",
        f"mode={'go' if go else 'dry-run'}",
        "keys: g=full h=hover p=pregrasp i=ingress o=open c=close q=quit",
    ]
    if plan is None:
        lines.append("No valid bottle target")
        return lines
    lines.append(f"target={plan.label} conf={plan.confidence:.2f} pixel={list(plan.pixel_xy)} depth={plan.depth_m:.3f}m")
    lines.append(
        f"center=({plan.grasp_center_m[0]:.3f}, {plan.grasp_center_m[1]:.3f}, {plan.grasp_center_m[2]:.3f})"
    )
    lines.append(
        f"approach=({plan.approach_dir_m[0]:.3f}, {plan.approach_dir_m[1]:.3f}, {plan.approach_dir_m[2]:.3f})"
    )
    lines.append(f"hover={plan.hover_pose[:3]}")
    lines.append(f"pregrasp={plan.pregrasp_pose[:3]}")
    lines.append(f"ingress={plan.ingress_pose[:3]}")
    lines.append(f"lift={plan.lift_pose[:3]}")
    return lines


def print_plan(plan: BottleTemplatePlan) -> None:
    print(f"Selected target: {plan.label} conf={plan.confidence:.3f}")
    print(f"Pixel center: {plan.pixel_xy}, depth={plan.depth_m:.4f} m")
    print(f"Camera point (m): {plan.point_camera_m.tolist()}")
    print(f"Base point (m): {plan.point_base_m.tolist()}")
    print(f"Corrected grasp center (m): {plan.grasp_center_m.tolist()}")
    print(f"Approach direction: {plan.approach_dir_m.tolist()}")
    print(f"Hover pose: {plan.hover_pose}")
    print(f"Pregrasp pose: {plan.pregrasp_pose}")
    print(f"Ingress pose: {plan.ingress_pose}")
    print(f"Lift pose: {plan.lift_pose}")
    print(f"Retreat pose: {plan.retreat_pose}")


def move_pose(robot: object | None, pose: list[float], execute: bool, label: str, send_order: str, mode_resend: int) -> None:
    print(f"{label}: {pose}")
    if robot is None or not execute:
        return
    send_hover_pose(robot, pose, send_order, mode_resend)
    time.sleep(0.4)


def open_hand(hand: OmniHandController | None, execute: bool) -> None:
    if hand is None:
        print("OmniHand open skipped (hand unavailable)")
        return
    if not execute:
        print("OmniHand open skipped (dry-run)")
        return
    hand.open()


def close_hand(hand: OmniHandController | None, execute: bool) -> None:
    if hand is None:
        print("OmniHand close skipped (hand unavailable)")
        return
    if not execute:
        print("OmniHand close skipped (dry-run)")
        return
    hand.close()


def execute_template(
    plan: BottleTemplatePlan,
    robot: object | None,
    hand: OmniHandController | None,
    args: argparse.Namespace,
) -> None:
    print_plan(plan)
    open_hand(hand, args.go)
    move_pose(robot, plan.hover_pose, args.go, "hover_pose", args.send_order, args.mode_resend)
    move_pose(robot, plan.pregrasp_pose, args.go, "pregrasp_pose", args.send_order, args.mode_resend)
    move_pose(robot, plan.ingress_pose, args.go, "ingress_pose", args.send_order, args.mode_resend)
    close_hand(hand, args.go)
    if args.go and args.hand_close_settle_s > 0:
        time.sleep(args.hand_close_settle_s)
    move_pose(robot, plan.lift_pose, args.go, "lift_pose", args.send_order, args.mode_resend)
    move_pose(robot, plan.retreat_pose, args.go, "retreat_pose", args.send_order, args.mode_resend)


def main() -> int:
    parser = parse_args()
    config_path = Path(parser.config).expanduser().resolve()
    config = load_yaml(config_path)
    repo_root = Path(__file__).resolve().parents[2]

    model_path = resolve_path(str(config["model"]), config_path, repo_root)
    calibration_path = resolve_path(str(config["calibration_file"]), config_path, repo_root)
    if not model_path.exists():
        raise SystemExit(f"Model file does not exist: {model_path}")
    if not calibration_path.exists():
        raise SystemExit(f"Calibration file does not exist: {calibration_path}")

    device = resolve_device(parser.device, parser.allow_cpu)
    base_to_camera = load_base_to_camera(calibration_path)
    model = YOLO(str(model_path))

    camera_cfg = config.get("camera", {})
    pipeline, align, profile = build_pipeline(
        camera_serial=str(camera_cfg.get("serial", "")),
        width=int(camera_cfg.get("width", 1280)),
        height=int(camera_cfg.get("height", 720)),
        fps=int(camera_cfg.get("fps", 30)),
        enable_depth=True,
    )
    assert align is not None
    intrinsics = intrinsics_from_profile(profile)

    robot_cfg = config.get("robot", {})
    robot = None
    if parser.go:
        robot = build_robot(str(robot_cfg.get("channel", "can0")), str(robot_cfg.get("model", "nero")))
        prepare_robot(robot, int(robot_cfg.get("speed_percent", 10)))

    hand_cfg = dict(config.get("hand", {})) if isinstance(config.get("hand", {}), dict) else {}
    hand_cfg["enabled"] = True
    hand = build_omnihand_controller(hand_cfg, execute=parser.go)

    window_name = "pick_lying_bottle_template"
    executed_once = False
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
                conf=float(config.get("workflow", {}).get("detection_conf", 0.25)),
                verbose=False,
                stream=False,
            )
            best = choose_target(results[0], depth_frame, intrinsics, base_to_camera, list(parser.target_labels))
            plan = build_plan(best, parser) if best is not None else None

            if not parser.no_display:
                annotated = image.copy()
                if best is not None:
                    draw_target_box(annotated, best)
                annotated = put_lines(annotated, overlay_lines(plan, parser.go))
                cv2.imshow(window_name, annotated)

            key = cv2.waitKey(1) & 0xFF if not parser.no_display else 255
            auto_execute = bool(parser.once and parser.no_display and plan is not None)
            if key == ord("q"):
                break
            if key == ord("o"):
                open_hand(hand, parser.go)
            if key == ord("c"):
                close_hand(hand, parser.go)
            if key == ord("h") and plan is not None:
                move_pose(robot, plan.hover_pose, parser.go, "hover_pose", parser.send_order, parser.mode_resend)
            if key == ord("p") and plan is not None:
                move_pose(robot, plan.pregrasp_pose, parser.go, "pregrasp_pose", parser.send_order, parser.mode_resend)
            if key == ord("i") and plan is not None:
                move_pose(robot, plan.ingress_pose, parser.go, "ingress_pose", parser.send_order, parser.mode_resend)

            if auto_execute or (key == ord("g") and plan is not None):
                execute_template(plan, robot, hand, parser)
                executed_once = True
                if parser.once:
                    break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

    return 0 if executed_once or not parser.once else 1


if __name__ == "__main__":
    sys.exit(main())
