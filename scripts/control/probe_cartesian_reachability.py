#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from itertools import product
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm
from _safety import check_pose_min_z

prefer_local_pyagxarm(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Cartesian reachability for a fixed orientation over a grid of XYZ positions."
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel")
    parser.add_argument("--robot", default="nero", help="Robot name for pyAgxArm")
    parser.add_argument("--start-pose", nargs=6, type=float, required=True, metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"))
    parser.add_argument("--mm", action="store_true", help="Interpret x/y/z inputs as millimeters")
    parser.add_argument("--degrees", action="store_true", help="Interpret roll/pitch/yaw inputs as degrees")
    parser.add_argument("--x-values", nargs="+", type=float, required=True, help="Probe X positions")
    parser.add_argument("--y-values", nargs="+", type=float, required=True, help="Probe Y positions")
    parser.add_argument("--z-values", nargs="+", type=float, required=True, help="Probe Z positions")
    parser.add_argument(
        "--fixed-rpy",
        nargs=3,
        type=float,
        default=None,
        metavar=("ROLL", "PITCH", "YAW"),
        help="Fixed orientation for every probe. Defaults to the orientation in --start-pose.",
    )
    parser.add_argument("--speed-percent", type=int, default=10)
    parser.add_argument("--send-order", default="mode_target_mode", choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"])
    parser.add_argument("--mode-resend", type=int, default=3)
    parser.add_argument("--wait-seconds", type=float, default=4.0)
    parser.add_argument("--sleep-between", type=float, default=0.2)
    parser.add_argument("--tolerance-mm", type=float, default=5.0)
    parser.add_argument("--tolerance-deg", type=float, default=3.0)
    parser.add_argument("--min-motion-mm", type=float, default=5.0)
    parser.add_argument("--min-rotation-deg", type=float, default=2.0)
    parser.add_argument("--return-to-start", action="store_true", help="Return to the start pose after every probe")
    parser.add_argument("--save-json", default="", help="Optional JSON path for probe results")
    parser.add_argument("--go", action="store_true", help="Actually send motion commands")
    return parser.parse_args()


def to_meters_if_needed(values: Sequence[float], mm: bool) -> list[float]:
    out = [float(v) for v in values]
    if mm:
        for i in range(min(3, len(out))):
            out[i] /= 1000.0
    return out


def to_radians_if_needed(values: Sequence[float], degrees: bool) -> list[float]:
    out = [float(v) for v in values]
    if degrees:
        for i in range(max(0, len(out) - 3), len(out)):
            out[i] = math.radians(out[i])
    return out


def wrap_angle_rad(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def angular_delta_rad(src: float, dst: float) -> float:
    return wrap_angle_rad(dst - src)


def pose_to_mm_deg(pose: Sequence[float]) -> list[float]:
    return [
        pose[0] * 1000.0,
        pose[1] * 1000.0,
        pose[2] * 1000.0,
        math.degrees(pose[3]),
        math.degrees(pose[4]),
        math.degrees(pose[5]),
    ]


def print_pose(label: str, pose: Sequence[float]) -> None:
    mm_deg = pose_to_mm_deg(pose)
    print(
        f"{label}: "
        f"x={mm_deg[0]:.1f} y={mm_deg[1]:.1f} z={mm_deg[2]:.1f} mm | "
        f"rx={mm_deg[3]:.1f} ry={mm_deg[4]:.1f} rz={mm_deg[5]:.1f} deg"
    )


def send_pose(robot: object, target_pose: Sequence[float], send_order: str, mode_resend: int) -> None:
    if not check_pose_min_z(list(target_pose), "probe_pose"):
        raise RuntimeError("Blocked by minimum z safety guard.")

    def send_mode_p() -> None:
        for _ in range(max(1, mode_resend)):
            robot.set_motion_mode("p")
            time.sleep(0.02)

    if send_order == "sdk":
        robot.move_p(list(target_pose))
        return
    if not hasattr(robot, "_deal_move_p_msgs") or not hasattr(robot, "_send_msgs"):
        raise RuntimeError("Selected send_order requires pyAgxArm driver internals.")
    msgs = robot._deal_move_p_msgs(list(target_pose))
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


def monitor_pose(
    robot: object,
    target_pose: Sequence[float],
    wait_seconds: float,
    tolerance_mm: float,
    tolerance_deg: float,
    min_motion_mm: float,
    min_rotation_deg: float,
) -> dict:
    base_msg = robot.get_flange_pose()
    base_pose = list(base_msg.msg) if base_msg is not None else None
    last_pose = None
    last_status = None
    best_translation_mm = None
    best_rotation_deg = None
    moved = False
    rotated = False

    start = time.time()
    while time.time() - start < wait_seconds:
        pose_msg = robot.get_flange_pose()
        if pose_msg is not None:
            last_pose = [float(v) for v in pose_msg.msg]
            if base_pose is not None:
                dist_mm = math.sqrt(sum(((last_pose[i] - base_pose[i]) * 1000.0) ** 2 for i in range(3)))
                rot_deg = max(abs(math.degrees(angular_delta_rad(base_pose[i], last_pose[i]))) for i in range(3, 6))
                moved = moved or dist_mm >= min_motion_mm
                rotated = rotated or rot_deg >= min_rotation_deg

            translation_err_mm = math.sqrt(sum(((last_pose[i] - target_pose[i]) * 1000.0) ** 2 for i in range(3)))
            rotation_err_deg = max(abs(math.degrees(angular_delta_rad(last_pose[i], target_pose[i]))) for i in range(3, 6))
            if best_translation_mm is None or translation_err_mm < best_translation_mm:
                best_translation_mm = translation_err_mm
            if best_rotation_deg is None or rotation_err_deg < best_rotation_deg:
                best_rotation_deg = rotation_err_deg
            if translation_err_mm <= tolerance_mm and rotation_err_deg <= tolerance_deg:
                break

        status_msg = robot.get_arm_status()
        if status_msg is not None:
            last_status = status_msg.msg
        time.sleep(0.05)

    translation_err_mm = None
    rotation_err_deg = None
    if last_pose is not None:
        translation_err_mm = math.sqrt(sum(((last_pose[i] - target_pose[i]) * 1000.0) ** 2 for i in range(3)))
        rotation_err_deg = max(abs(math.degrees(angular_delta_rad(last_pose[i], target_pose[i]))) for i in range(3, 6))

    reached = (
        translation_err_mm is not None
        and rotation_err_deg is not None
        and translation_err_mm <= tolerance_mm
        and rotation_err_deg <= tolerance_deg
    )
    return {
        "success": reached,
        "moved": moved,
        "rotated": rotated,
        "last_pose": last_pose,
        "last_status": str(last_status) if last_status is not None else None,
        "translation_err_mm": translation_err_mm,
        "rotation_err_deg": rotation_err_deg,
        "best_translation_err_mm": best_translation_mm,
        "best_rotation_err_deg": best_rotation_deg,
    }


def main() -> int:
    args = parse_args()
    start_pose = to_radians_if_needed(to_meters_if_needed(args.start_pose, args.mm), args.degrees)
    fixed_rpy = (
        to_radians_if_needed(list(args.fixed_rpy), args.degrees)
        if args.fixed_rpy is not None
        else [float(v) for v in start_pose[3:]]
    )

    x_values = [float(v) / 1000.0 if args.mm else float(v) for v in args.x_values]
    y_values = [float(v) / 1000.0 if args.mm else float(v) for v in args.y_values]
    z_values = [float(v) / 1000.0 if args.mm else float(v) for v in args.z_values]

    probe_poses = [[x, y, z, *fixed_rpy] for x, y, z in product(x_values, y_values, z_values)]
    print_pose("Start pose", start_pose)
    print(f"Probe count: {len(probe_poses)}")
    for idx, pose in enumerate(probe_poses, start=1):
        print_pose(f"Probe {idx:02d}", pose)

    results = {
        "start_pose_mm_deg": pose_to_mm_deg(start_pose),
        "probe_count": len(probe_poses),
        "probes": [],
    }
    if not args.go:
        print("Dry run: pass --go to execute the probes.")
        if args.save_json:
            Path(args.save_json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    from pyAgxArm import AgxArmFactory, create_agx_arm_config

    cfg = create_agx_arm_config(robot=args.robot, comm="can", channel=args.channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    if hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
        print("set_normal_mode sent.")
    ok = robot.enable()
    print("enable (immediate):", ok)
    time.sleep(0.3)
    robot.set_speed_percent(args.speed_percent)

    print("Moving to start pose...")
    send_pose(robot, start_pose, args.send_order, args.mode_resend)
    time.sleep(args.wait_seconds)

    for idx, pose in enumerate(probe_poses, start=1):
        print()
        print(f"=== Probe {idx}/{len(probe_poses)} ===")
        print_pose("Command pose", pose)
        send_pose(robot, pose, args.send_order, args.mode_resend)
        monitor = monitor_pose(
            robot=robot,
            target_pose=pose,
            wait_seconds=args.wait_seconds,
            tolerance_mm=args.tolerance_mm,
            tolerance_deg=args.tolerance_deg,
            min_motion_mm=args.min_motion_mm,
            min_rotation_deg=args.min_rotation_deg,
        )
        if monitor["last_pose"] is not None:
            print_pose("Last flange pose", monitor["last_pose"])
        translation_text = "n/a" if monitor["translation_err_mm"] is None else f"{monitor['translation_err_mm']:.2f}"
        rotation_text = "n/a" if monitor["rotation_err_deg"] is None else f"{monitor['rotation_err_deg']:.2f}"
        print(
            f"Reachability: success={monitor['success']} "
            f"translation={translation_text} mm "
            f"rotation={rotation_text} deg"
        )
        results["probes"].append(
            {
                "command_pose_mm_deg": pose_to_mm_deg(pose),
                "success": monitor["success"],
                "translation_err_mm": monitor["translation_err_mm"],
                "rotation_err_deg": monitor["rotation_err_deg"],
                "best_translation_err_mm": monitor["best_translation_err_mm"],
                "best_rotation_err_deg": monitor["best_rotation_err_deg"],
                "last_pose_mm_deg": pose_to_mm_deg(monitor["last_pose"]) if monitor["last_pose"] is not None else None,
                "last_status": monitor["last_status"],
            }
        )
        if args.return_to_start:
            print("Returning to start pose...")
            send_pose(robot, start_pose, args.send_order, args.mode_resend)
            time.sleep(args.wait_seconds)
        if args.sleep_between > 0:
            time.sleep(args.sleep_between)

    if args.save_json:
        Path(args.save_json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved results to {args.save_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
