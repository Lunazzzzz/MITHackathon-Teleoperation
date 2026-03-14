#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect a target and move/preview a hover pose above it in the robot base frame."
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
    parser.add_argument("--target-labels", nargs="*", default=DEFAULT_TARGET_LABELS, help="Semantic target labels to keep")
    parser.add_argument(
        "--debug-topk",
        type=int,
        default=5,
        help="Show the top-K raw detections in the overlay and terminal for debugging class confusion.",
    )
    parser.add_argument(
        "--keep-last-seconds",
        type=float,
        default=1.5,
        help="Keep showing and using the last valid target for this many seconds when detection flickers.",
    )
    parser.add_argument("--hover-height-m", type=float, default=0.30, help="Hover offset above detected base Z")
    parser.add_argument(
        "--base-offset-m",
        nargs=3,
        type=float,
        default=[0.0, 0.0, 0.0],
        metavar=("DX", "DY", "DZ"),
        help="Initial base-frame XYZ offset applied before hover height; can also be tuned at runtime via keys.",
    )
    parser.add_argument(
        "--offset-step-m",
        type=float,
        default=0.01,
        help="Offset step size for runtime keyboard tuning.",
    )
    parser.add_argument(
        "--pose-rpy-deg",
        nargs=3,
        type=float,
        default=[90.0, -90.0, 0.0],
        metavar=("ROLL", "PITCH", "YAW"),
        help="Fixed hover orientation in degrees",
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel")
    parser.add_argument("--robot", default="nero", help="Robot model for pyAgxArm")
    parser.add_argument("--speed-percent", type=int, default=10, help="Robot speed percent")
    parser.add_argument("--send-order", default="mode_target_mode", choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"])
    parser.add_argument("--mode-resend", type=int, default=3, help="How many times to resend motion mode")
    parser.add_argument(
        "--post-move-wait-seconds",
        type=float,
        default=2.5,
        help="Seconds to wait after sending hover motion before reading back the robot pose.",
    )
    parser.add_argument(
        "--follow-rate-hz",
        type=float,
        default=30.0,
        help="Maximum command send rate while follow mode is enabled.",
    )
    parser.add_argument("--go", action="store_true", help="Actually send the hover motion when pressing g")
    parser.add_argument("--save-json", default="", help="Optional JSONL file for detections and hover poses")
    return parser.parse_args()


def load_base_to_camera(path_str: str) -> tuple[Path, np.ndarray]:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Calibration file does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    try:
        matrix = data["transforms"]["T_base_camera"]["matrix"]
    except Exception as exc:
        raise SystemExit(f"Calibration file is missing transforms.T_base_camera.matrix: {path}") from exc
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.shape != (4, 4):
        raise SystemExit(f"T_base_camera must be 4x4, got {mat.shape} from {path}")
    return path, mat


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


def ensure_robot_enabled(robot: object, timeout_s: float = 2.5) -> list[bool] | None:
    states = None
    try:
        states = robot.get_joints_enable_status_list()
    except Exception:
        states = None
    if states is not None and all(states):
        return states

    if hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
    robot.enable()
    deadline = time.time() + max(0.0, timeout_s)
    while time.time() < deadline:
        try:
            states = robot.get_joints_enable_status_list()
        except Exception:
            states = None
        if states is not None and all(states):
            return states
        time.sleep(0.05)
    return states


def clone_row(row: dict[str, object] | None) -> dict[str, object] | None:
    if row is None:
        return None
    cloned = dict(row)
    for key in ["bbox_xyxy", "center_xy", "camera_xyz_m", "base_xyz_m"]:
        if cloned.get(key) is not None:
            cloned[key] = [float(v) for v in cloned[key]]
    return cloned


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


def rotation_error_deg(target_pose: list[float], current_pose: list[float]) -> float:
    rot_target = rpy_to_rot(target_pose[3], target_pose[4], target_pose[5])
    rot_current = rpy_to_rot(current_pose[3], current_pose[4], current_pose[5])
    delta = rot_target.T @ rot_current
    trace = np.clip((np.trace(delta) - 1.0) * 0.5, -1.0, 1.0)
    return float(np.degrees(np.arccos(trace)))


def read_flange_pose(robot: object, timeout_s: float = 2.0) -> list[float] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pose_msg = robot.get_flange_pose()
        if pose_msg is not None:
            return [float(v) for v in pose_msg.msg]
        time.sleep(0.05)
    return None


def send_hover_pose(robot: object, hover_pose: list[float], send_order: str, mode_resend: int) -> None:
    def send_mode_p() -> None:
        for _ in range(max(1, mode_resend)):
            robot.set_motion_mode("p")
            time.sleep(0.02)

    if send_order == "sdk":
        robot.move_p(hover_pose)
        return

    if not hasattr(robot, "_deal_move_p_msgs") or not hasattr(robot, "_send_msgs"):
        raise SystemExit("Requested send_order requires pyAgxArm driver internals (_deal_move_p_msgs/_send_msgs).")

    msgs = robot._deal_move_p_msgs(hover_pose)
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
        raise SystemExit(f"Unknown send_order: {send_order}")


def draw_target_box(image: np.ndarray, row: dict[str, object], *, primary: bool) -> None:
    x1, y1, x2, y2 = [int(v) for v in row["bbox_xyxy"]]
    cx, cy = [int(v) for v in row["center_xy"]]
    if bool(row.get("stale")):
        color = (120, 220, 220)
    else:
        color = (0, 220, 0) if primary else (0, 160, 255)
    thickness = 3 if primary else 2
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    cv2.circle(image, (cx, cy), 5, color, -1)
    cv2.drawMarker(image, (cx, cy), color, cv2.MARKER_CROSS, 18, 2)


def overlay_lines(
    row: dict[str, object] | None,
    hover_pose: list[float] | None,
    calibration_path: Path,
    go: bool,
    debug_rows: list[dict[str, object]],
    *,
    follow_enabled: bool,
    follow_rate_hz: float,
    base_offset_m: list[float],
    offset_step_m: float,
) -> list[str]:
    lines = [
        "Hover target above detected object",
        f"calibration={calibration_path.name}",
        f"mode={'go' if go else 'dry-run'}",
        f"follow={'ON' if follow_enabled else 'OFF'} @{follow_rate_hz:.1f}Hz",
        f"offset=({base_offset_m[0]:.3f}, {base_offset_m[1]:.3f}, {base_offset_m[2]:.3f}) step={offset_step_m:.3f}m",
    ]
    if row is None or hover_pose is None:
        lines.append("No valid target")
        lines.append("Offset keys: a/d=X-/X+, w/s=Y+/Y-, r/v=Z+/Z-, x=reset")
        lines.append("Press f to toggle follow, g for single-shot, q to quit")
        return lines
    cam = row["camera_xyz_m"]
    base = row["base_xyz_m"]
    label_text = str(row["class_name"])
    if row.get("target_name") and row["target_name"] != row["class_name"]:
        label_text = f"{row['class_name']}->{row['target_name']}"
    if bool(row.get("stale")):
        label_text += " stale"
    lines.append(f"{label_text} conf={float(row['confidence']):.2f} pixel={[int(v) for v in row['center_xy']]}")
    lines.append(f"cam=({cam[0]:.3f}, {cam[1]:.3f}, {cam[2]:.3f})")
    lines.append(f"base=({base[0]:.3f}, {base[1]:.3f}, {base[2]:.3f})")
    lines.append(
        f"hover=({hover_pose[0]:.3f}, {hover_pose[1]:.3f}, {hover_pose[2]:.3f}, "
        f"{hover_pose[3]:.3f}, {hover_pose[4]:.3f}, {hover_pose[5]:.3f})"
    )
    if debug_rows:
        debug_text = ", ".join(f"{r['class_name']}:{float(r['confidence']):.2f}" for r in debug_rows)
        lines.append(f"top={debug_text}")
    lines.append("Offset keys: a/d=X-/X+, w/s=Y+/Y-, r/v=Z+/Z-, x=reset")
    lines.append("Press f to toggle follow, g for single-shot, q to quit")
    return lines


def main() -> int:
    args = parse_args()
    model_path = resolve_path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model file does not exist: {model_path}")

    calibration_path, base_to_camera = load_base_to_camera(args.calibration_file)
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
    target_labels = list(args.target_labels)
    target_label_set = set(target_labels)
    target_priority = {label: idx for idx, label in enumerate(target_labels)}
    pose_rpy_rad = [float(np.deg2rad(v)) for v in args.pose_rpy_deg]
    base_offset_m = [float(v) for v in args.base_offset_m]
    output_path = Path(args.save_json).expanduser().resolve() if args.save_json else None
    output_handle = output_path.open("a", encoding="utf-8") if output_path else None

    robot = None
    if args.go:
        robot = build_robot(args.channel, args.robot)
        prepare_robot(robot, args.speed_percent)

    window_name = "hover_detected_target"
    last_print_s = 0.0
    last_valid_row: dict[str, object] | None = None
    last_valid_hover_pose: list[float] | None = None
    last_valid_ts = 0.0
    last_key = -1
    follow_enabled = False
    last_follow_send_ts = 0.0
    follow_interval_s = 1.0 / max(1e-3, args.follow_rate_hz)
    last_follow_print_ts = 0.0

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
            result = results[0]
            rows: list[dict[str, object]] = []
            raw_rows = detection_rows(result)
            debug_rows = sorted(raw_rows, key=lambda row: float(row["confidence"]), reverse=True)[: max(0, args.debug_topk)]
            for row in raw_rows:
                original_name = str(row["class_name"])
                target_name = CLASS_ALIASES.get(original_name, original_name)
                row["target_name"] = target_name
                if target_label_set and target_name not in target_label_set:
                    continue
                cx, cy = [int(v) for v in row["center_xy"]]
                depth_m = sample_depth_m(depth_frame, cx, cy, args.depth_window)
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
                    target_priority.get(str(row.get("target_name", row["class_name"])), len(target_priority)),
                    -float(row["confidence"]),
                )
            )

            best = rows[0] if rows else None
            hover_pose = None
            if best is not None:
                base = best["base_xyz_m"]
                hover_pose = [
                    float(base[0] + base_offset_m[0]),
                    float(base[1] + base_offset_m[1]),
                    float(base[2] + base_offset_m[2] + args.hover_height_m),
                    *pose_rpy_rad,
                ]
                last_valid_row = clone_row(best)
                last_valid_hover_pose = [float(v) for v in hover_pose]
                last_valid_ts = time.time()
            elif last_valid_row is not None and time.time() - last_valid_ts <= max(0.0, args.keep_last_seconds):
                best = clone_row(last_valid_row)
                hover_pose = [float(v) for v in last_valid_hover_pose] if last_valid_hover_pose is not None else None
                if best is not None:
                    best["stale"] = True

            annotated = image.copy()
            if best is not None:
                draw_target_box(annotated, best, primary=True)
            annotated = put_lines(
                annotated,
                overlay_lines(
                    best,
                    hover_pose,
                    calibration_path,
                    args.go,
                    debug_rows,
                    follow_enabled=follow_enabled,
                    follow_rate_hz=args.follow_rate_hz,
                    base_offset_m=base_offset_m,
                    offset_step_m=args.offset_step_m,
                ),
            )

            if output_handle is not None:
                payload = {
                    "timestamp_unix": time.time(),
                    "best_detection": best,
                    "debug_topk": debug_rows,
                    "hover_pose_m_rad": hover_pose,
                }
                output_handle.write(json_dumps(payload) + "\n")
                output_handle.flush()

            now = time.time()
            if now - last_print_s >= 1.0:
                if best is not None and hover_pose is not None:
                    label_text = str(best["class_name"])
                    if best.get("target_name") and best["target_name"] != best["class_name"]:
                        label_text = f"{best['class_name']}->{best['target_name']}"
                    print(
                        f"{label_text} conf={best['confidence']:.3f} "
                        f"camera_xyz={best['camera_xyz_m']} base_xyz={best['base_xyz_m']} "
                        f"hover_pose={hover_pose}"
                    )
                if debug_rows:
                    print("top detections:", ", ".join(f"{r['class_name']}:{float(r['confidence']):.3f}" for r in debug_rows))
                last_print_s = now

            cv2.imshow(window_name, annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            offset_changed = False
            if key == ord("a"):
                base_offset_m[0] -= args.offset_step_m
                offset_changed = True
            elif key == ord("d"):
                base_offset_m[0] += args.offset_step_m
                offset_changed = True
            elif key == ord("w"):
                base_offset_m[1] += args.offset_step_m
                offset_changed = True
            elif key == ord("s"):
                base_offset_m[1] -= args.offset_step_m
                offset_changed = True
            elif key == ord("r"):
                base_offset_m[2] += args.offset_step_m
                offset_changed = True
            elif key == ord("v"):
                base_offset_m[2] -= args.offset_step_m
                offset_changed = True
            elif key == ord("x"):
                base_offset_m = [float(v) for v in args.base_offset_m]
                offset_changed = True
            if offset_changed:
                print(
                    "Updated base offset (m):",
                    [round(base_offset_m[0], 4), round(base_offset_m[1], 4), round(base_offset_m[2], 4)],
                )
            toggle_follow = key == ord("f") and last_key != ord("f")
            trigger_hover = key == ord("g") and last_key != ord("g")
            last_key = key
            if toggle_follow:
                follow_enabled = not follow_enabled
                state = "enabled" if follow_enabled else "disabled"
                print(f"Follow mode {state} at up to {args.follow_rate_hz:.1f} Hz.")
                if not follow_enabled:
                    last_follow_send_ts = 0.0

            if follow_enabled and robot is not None and best is not None and hover_pose is not None:
                now = time.time()
                if now - last_follow_send_ts >= follow_interval_s:
                    enabled_states = ensure_robot_enabled(robot)
                    if enabled_states is None or not all(enabled_states):
                        print(f"Follow mode skipped send; joints not enabled: {enabled_states}")
                    else:
                        if check_pose_min_z(hover_pose, "hover_pose"):
                            send_hover_pose(robot, [float(v) for v in hover_pose], args.send_order, args.mode_resend)
                            last_follow_send_ts = now
                            if now - last_follow_print_ts >= 1.0:
                                label_text = str(best["class_name"])
                                if best.get("target_name") and best["target_name"] != best["class_name"]:
                                    label_text = f"{best['class_name']}->{best['target_name']}"
                                if bool(best.get("stale")):
                                    label_text += " stale"
                                print(f"Follow command sent: {label_text} hover_pose={[float(v) for v in hover_pose]}")
                                last_follow_print_ts = now

            if trigger_hover and best is not None and hover_pose is not None:
                locked_hover_pose = [float(v) for v in hover_pose]
                label_text = str(best["class_name"])
                if best.get("target_name") and best["target_name"] != best["class_name"]:
                    label_text = f"{best['class_name']}->{best['target_name']}"
                if bool(best.get("stale")):
                    label_text += " stale"
                print(f"Selected target: {label_text} hover_pose={locked_hover_pose}")
                if robot is not None:
                    if not check_pose_min_z(locked_hover_pose, "hover_pose"):
                        continue
                    enabled_states = ensure_robot_enabled(robot)
                    print(f"Enabled joints before send: {enabled_states}")
                    before_pose = read_flange_pose(robot, timeout_s=1.0)
                    if before_pose is not None:
                        print(f"Flange pose before: {before_pose}")
                    send_hover_pose(robot, locked_hover_pose, args.send_order, args.mode_resend)
                    print("Hover motion sent.")
                    time.sleep(max(0.0, args.post_move_wait_seconds))
                    after_pose = read_flange_pose(robot, timeout_s=1.0)
                    if after_pose is not None:
                        dx = (after_pose[0] - locked_hover_pose[0]) * 1000.0
                        dy = (after_pose[1] - locked_hover_pose[1]) * 1000.0
                        dz = (after_pose[2] - locked_hover_pose[2]) * 1000.0
                        err_mm = (dx * dx + dy * dy + dz * dz) ** 0.5
                        rot_err_deg = rotation_error_deg(locked_hover_pose, after_pose)
                        print(f"Flange pose after:  {after_pose}")
                        print(
                            f"Hover pose error: translation={err_mm:.2f} mm "
                            f"rotation={rot_err_deg:.2f} deg"
                        )
                    else:
                        print("Flange pose after: unavailable")
                else:
                    print("Dry run: add --go to send the hover motion.")
    finally:
        if output_handle is not None:
            output_handle.close()
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


def json_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
