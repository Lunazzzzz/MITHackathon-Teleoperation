#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm
from _safety import check_pose_min_z

prefer_local_pyagxarm(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move NERO flange pose in small Cartesian steps from a known-good pose to a target pose."
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel, e.g. can0")
    parser.add_argument("--robot", default="nero", help="Robot name passed into pyAgxArm (default: nero)")
    parser.add_argument(
        "--start-pose",
        nargs=6,
        type=float,
        required=True,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        help="Known-good start flange pose [x y z roll pitch yaw].",
    )
    parser.add_argument(
        "--target-pose",
        nargs=6,
        type=float,
        required=True,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        help="Target flange pose [x y z roll pitch yaw].",
    )
    parser.add_argument(
        "--mm",
        action="store_true",
        help="Interpret x/y/z as millimeters.",
    )
    parser.add_argument(
        "--degrees",
        action="store_true",
        help="Interpret roll/pitch/yaw as degrees.",
    )
    parser.add_argument(
        "--speed-percent",
        type=int,
        default=20,
        help="Speed percent [0..100]. Default: 20.",
    )
    parser.add_argument(
        "--send-order",
        default="mode_target_mode",
        choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"],
        help="How to send the Cartesian command. Default: mode_target_mode.",
    )
    parser.add_argument(
        "--mode-resend",
        type=int,
        default=3,
        help="How many times to resend the motion mode command. Default: 3.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=5.0,
        help="Seconds to monitor each step after sending. Default: 5.0.",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=0.2,
        help="Pause between successful steps. Default: 0.2s.",
    )
    parser.add_argument(
        "--position-step-mm",
        type=float,
        default=20.0,
        help="Maximum per-step translation delta for the position phase in mm. Default: 20.",
    )
    parser.add_argument(
        "--rotation-step-deg",
        type=float,
        default=10.0,
        help="Maximum per-step rotation delta for the orientation phase in degrees. Default: 10.",
    )
    parser.add_argument(
        "--tolerance-mm",
        type=float,
        default=5.0,
        help="Translation tolerance for considering a step reached. Default: 5 mm.",
    )
    parser.add_argument(
        "--tolerance-deg",
        type=float,
        default=3.0,
        help="Rotation tolerance for considering a step reached. Default: 3 deg.",
    )
    parser.add_argument(
        "--min-motion-mm",
        type=float,
        default=5.0,
        help="Consider translation motion detected above this threshold. Default: 5 mm.",
    )
    parser.add_argument(
        "--min-rotation-deg",
        type=float,
        default=2.0,
        help="Consider rotation motion detected above this threshold. Default: 2 deg.",
    )
    parser.add_argument(
        "--no-normal-mode",
        action="store_true",
        help="Do not call robot.set_normal_mode() before enabling/moving.",
    )
    parser.add_argument(
        "--no-enable",
        action="store_true",
        help="Do not call robot.enable() before moving.",
    )
    parser.add_argument(
        "--path-mode",
        default="position_then_orientation",
        choices=["position_then_orientation", "combined"],
        help="Interpolate position and rotation separately or together. Default: position_then_orientation.",
    )
    parser.add_argument(
        "--save-json",
        default="",
        help="Optional JSON file to save the planned steps and step results.",
    )
    parser.add_argument(
        "--go",
        action="store_true",
        help="Actually send the motion commands. Without this flag the script only prints the step plan.",
    )
    return parser.parse_args()


def to_meters_if_needed(pose: Sequence[float], mm: bool) -> list[float]:
    out = [float(v) for v in pose]
    if mm:
        out[0] /= 1000.0
        out[1] /= 1000.0
        out[2] /= 1000.0
    return out


def to_radians_if_needed(pose: Sequence[float], degrees: bool) -> list[float]:
    out = [float(v) for v in pose]
    if degrees:
        out[3] = math.radians(out[3])
        out[4] = math.radians(out[4])
        out[5] = math.radians(out[5])
    return out


def wrap_angle_rad(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def angular_delta_rad(src: float, dst: float) -> float:
    return wrap_angle_rad(dst - src)


def lerp_translation(src: Sequence[float], dst: Sequence[float], t: float) -> list[float]:
    return [float(src[i] + (dst[i] - src[i]) * t) for i in range(3)]


def lerp_rotation(src: Sequence[float], dst: Sequence[float], t: float) -> list[float]:
    return [float(src[i] + angular_delta_rad(src[i], dst[i]) * t) for i in range(3)]


def pose_to_mm_deg(pose: Sequence[float]) -> list[float]:
    return [
        pose[0] * 1000.0,
        pose[1] * 1000.0,
        pose[2] * 1000.0,
        math.degrees(pose[3]),
        math.degrees(pose[4]),
        math.degrees(pose[5]),
    ]


def build_steps(
    start_pose: Sequence[float],
    target_pose: Sequence[float],
    position_step_mm: float,
    rotation_step_deg: float,
    path_mode: str,
) -> list[dict]:
    steps: list[dict] = []

    dx_mm = max(abs((target_pose[i] - start_pose[i]) * 1000.0) for i in range(3))
    dr_deg = max(abs(math.degrees(angular_delta_rad(start_pose[i], target_pose[i]))) for i in range(3, 6))

    if path_mode == "combined":
        move_steps = max(
            int(math.ceil(dx_mm / max(position_step_mm, 1e-6))),
            int(math.ceil(dr_deg / max(rotation_step_deg, 1e-6))),
            1,
        )
        for idx in range(1, move_steps + 1):
            t = idx / move_steps
            pose = lerp_translation(start_pose[:3], target_pose[:3], t) + lerp_rotation(start_pose[3:], target_pose[3:], t)
            steps.append({"stage": "combined", "index": idx, "count": move_steps, "pose": pose})
        return steps

    pos_steps = int(math.ceil(dx_mm / max(position_step_mm, 1e-6))) if dx_mm > 0 else 0
    rot_steps = int(math.ceil(dr_deg / max(rotation_step_deg, 1e-6))) if dr_deg > 0 else 0

    if pos_steps == 0 and rot_steps == 0:
        steps.append({"stage": "hold", "index": 1, "count": 1, "pose": [float(v) for v in target_pose]})
        return steps

    for idx in range(1, pos_steps + 1):
        t = idx / pos_steps
        pose = lerp_translation(start_pose[:3], target_pose[:3], t) + [float(v) for v in start_pose[3:]]
        steps.append({"stage": "position", "index": idx, "count": pos_steps, "pose": pose})

    if rot_steps:
        rotation_start = steps[-1]["pose"] if steps else [float(v) for v in start_pose]
        for idx in range(1, rot_steps + 1):
            t = idx / rot_steps
            pose = [float(v) for v in target_pose[:3]] + lerp_rotation(rotation_start[3:], target_pose[3:], t)
            steps.append({"stage": "orientation", "index": idx, "count": rot_steps, "pose": pose})

    return steps


def send_pose(robot: object, target_pose: Sequence[float], send_order: str, mode_resend: int) -> None:
    if not check_pose_min_z(list(target_pose), "sweep_pose"):
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

    status_text = str(getattr(last_status, "motion_status", "")) if last_status is not None else ""
    reached = (
        translation_err_mm is not None
        and rotation_err_deg is not None
        and translation_err_mm <= tolerance_mm
        and rotation_err_deg <= tolerance_deg
    )
    success = reached or ("SUCCESSFULLY" in status_text and (moved or rotated))

    return {
        "success": success,
        "moved": moved,
        "rotated": rotated,
        "last_pose": last_pose,
        "last_status": str(last_status) if last_status is not None else None,
        "translation_err_mm": translation_err_mm,
        "rotation_err_deg": rotation_err_deg,
        "best_translation_err_mm": best_translation_mm,
        "best_rotation_err_deg": best_rotation_deg,
    }


def print_pose(label: str, pose: Sequence[float]) -> None:
    mm_deg = pose_to_mm_deg(pose)
    print(
        f"{label}: "
        f"x={mm_deg[0]:.3f} y={mm_deg[1]:.3f} z={mm_deg[2]:.3f} mm | "
        f"rx={mm_deg[3]:.3f} ry={mm_deg[4]:.3f} rz={mm_deg[5]:.3f} deg"
    )


def main() -> int:
    args = parse_args()

    try:
        from pyAgxArm import AgxArmFactory, create_agx_arm_config
    except ImportError as exc:
        raise SystemExit("pyAgxArm is not installed. Run: python3 -m pip install -e ./pyAgxArm") from exc

    start_pose = to_radians_if_needed(to_meters_if_needed(args.start_pose, args.mm), args.degrees)
    target_pose = to_radians_if_needed(to_meters_if_needed(args.target_pose, args.mm), args.degrees)
    steps = build_steps(start_pose, target_pose, args.position_step_mm, args.rotation_step_deg, args.path_mode)

    print_pose("Start pose", start_pose)
    print_pose("Target pose", target_pose)
    print(f"Path mode: {args.path_mode}")
    print(f"Planned steps: {len(steps)}")
    for idx, step in enumerate(steps, start=1):
        print_pose(f"Step {idx:02d} [{step['stage']} {step['index']}/{step['count']}]", step["pose"])

    results: dict = {
        "start_pose_mm_deg": pose_to_mm_deg(start_pose),
        "target_pose_mm_deg": pose_to_mm_deg(target_pose),
        "path_mode": args.path_mode,
        "steps": [],
    }

    if not args.go:
        print("Dry run: pass --go to execute the sweep.")
        if args.save_json:
            Path(args.save_json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    cfg = create_agx_arm_config(robot=args.robot, comm="can", channel=args.channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()

    status = robot.get_arm_status()
    if status is not None:
        print("Arm status before sweep:", status.msg)
    current = robot.get_flange_pose()
    if current is not None:
        print_pose("Current flange pose", current.msg)

    if not args.no_normal_mode and hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
        print("set_normal_mode sent.")

    if not args.no_enable:
        ok = robot.enable()
        print("enable (immediate):", ok)
        deadline = time.time() + 3.0
        last_states = None
        while time.time() < deadline:
            try:
                states = robot.get_joints_enable_status_list()
            except Exception:
                states = None
            if states is not None:
                last_states = states
                if all(states):
                    break
            time.sleep(0.05)
        print("enabled joints:", last_states if last_states is not None else "(not available)")

    robot.set_speed_percent(args.speed_percent)

    for idx, step in enumerate(steps, start=1):
        print()
        print(f"=== Executing step {idx}/{len(steps)} [{step['stage']} {step['index']}/{step['count']}] ===")
        print_pose("Command pose", step["pose"])
        send_pose(robot, step["pose"], args.send_order, args.mode_resend)
        print(f"move_p sent ({args.send_order}, mode_resend={args.mode_resend}).")
        monitor = monitor_pose(
            robot=robot,
            target_pose=step["pose"],
            wait_seconds=args.wait_seconds,
            tolerance_mm=args.tolerance_mm,
            tolerance_deg=args.tolerance_deg,
            min_motion_mm=args.min_motion_mm,
            min_rotation_deg=args.min_rotation_deg,
        )
        if monitor["last_pose"] is not None:
            print_pose("Last flange pose", monitor["last_pose"])
        if monitor["translation_err_mm"] is not None and monitor["rotation_err_deg"] is not None:
            print(
                "Errors: "
                f"translation={monitor['translation_err_mm']:.2f} mm "
                f"(best {monitor['best_translation_err_mm']:.2f} mm), "
                f"rotation={monitor['rotation_err_deg']:.2f} deg "
                f"(best {monitor['best_rotation_err_deg']:.2f} deg)"
            )
        if monitor["last_status"] is not None:
            print("Last arm status:", monitor["last_status"])

        step_result = {
            "step": idx,
            "stage": step["stage"],
            "command_pose_mm_deg": pose_to_mm_deg(step["pose"]),
            "success": monitor["success"],
            "translation_err_mm": monitor["translation_err_mm"],
            "rotation_err_deg": monitor["rotation_err_deg"],
            "best_translation_err_mm": monitor["best_translation_err_mm"],
            "best_rotation_err_deg": monitor["best_rotation_err_deg"],
            "moved": monitor["moved"],
            "rotated": monitor["rotated"],
            "last_pose_mm_deg": pose_to_mm_deg(monitor["last_pose"]) if monitor["last_pose"] is not None else None,
            "last_status": monitor["last_status"],
        }
        results["steps"].append(step_result)

        if not monitor["success"]:
            print(f"Step {idx} failed. Sweep stopped.")
            if args.save_json:
                Path(args.save_json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

        if args.sleep_between > 0:
            time.sleep(args.sleep_between)

    print()
    print("Sweep finished successfully.")
    if args.save_json:
        Path(args.save_json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved results to {args.save_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
