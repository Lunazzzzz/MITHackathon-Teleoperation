#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Sequence

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm
from _safety import check_pose_min_z

prefer_local_pyagxarm(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move NERO to a target pose using pyAgxArm (CAN)."
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel, e.g. can0")
    parser.add_argument("--robot", default="nero", help="Robot name passed into pyAgxArm (default: nero)")
    parser.add_argument(
        "--pose",
        nargs=6,
        type=float,
        required=True,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        help="Target pose [x y z roll pitch yaw]. Units: meters + radians (unless --degrees).",
    )
    parser.add_argument(
        "--target-frame",
        choices=["flange", "tcp"],
        default="flange",
        help="Interpret --pose as a flange pose or a TCP pose in the base frame. Default: flange.",
    )
    parser.add_argument(
        "--mm",
        action="store_true",
        help="Interpret x/y/z as millimeters (will be converted to meters).",
    )
    parser.add_argument(
        "--degrees",
        action="store_true",
        help="Interpret roll/pitch/yaw as degrees (will be converted to radians).",
    )
    parser.add_argument(
        "--tcp-offset",
        nargs=6,
        type=float,
        default=None,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        help="TCP offset pose relative to flange. Units: meters + radians (unless --tcp-offset-mm/--tcp-offset-degrees).",
    )
    parser.add_argument(
        "--tcp-offset-yaml",
        default="",
        help="Optional YAML file containing a 6-element TCP offset pose or a pose6/tcp_offset_pose field.",
    )
    parser.add_argument(
        "--tcp-offset-mm",
        action="store_true",
        help="Interpret TCP offset x/y/z as millimeters.",
    )
    parser.add_argument(
        "--tcp-offset-degrees",
        action="store_true",
        help="Interpret TCP offset roll/pitch/yaw as degrees.",
    )
    parser.add_argument(
        "--speed-percent",
        type=int,
        default=20,
        help="Speed percent [0..100]. Default: 20 (safer).",
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
        "--enable-timeout",
        type=float,
        default=3.0,
        help="Seconds to wait for joints to become enabled (best-effort). Default: 3.0.",
    )
    parser.add_argument(
        "--go",
        action="store_true",
        help="Actually send the motion command. Without this flag, the script only prints what it would do.",
    )
    parser.add_argument(
        "--sleep-after",
        type=float,
        default=0.0,
        help="Optional sleep seconds after sending the command (for logs/observation).",
    )
    parser.add_argument(
        "--send-order",
        default="sdk",
        choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"],
        help=(
            "How to send commands. "
            "'sdk' uses robot.move_p(). "
            "'target_then_mode' sends target pose messages first, then sends mode (matches many CAN protocols). "
            "'mode_then_target' sends mode first, then target pose messages. "
            "'mode_target_mode' sends mode, then target, then mode again (robust against controller expectations)."
        ),
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=3.0,
        help="Seconds to monitor flange pose after sending command. Default: 3.0.",
    )
    parser.add_argument(
        "--min-motion-mm",
        type=float,
        default=2.0,
        help="Consider motion detected if translation changes by this many mm. Default: 2.0.",
    )
    parser.add_argument(
        "--tolerance-mm",
        type=float,
        default=2.0,
        help="Stop waiting early if translation error to target is within this many mm. Default: 2.0.",
    )
    parser.add_argument(
        "--tolerance-deg",
        type=float,
        default=3.0,
        help="Stop waiting early if rotation error to target is within this many deg. Default: 3.0.",
    )
    parser.add_argument(
        "--mode-resend",
        type=int,
        default=1,
        help="How many times to resend the motion mode command (best-effort). Default: 1.",
    )
    return parser.parse_args()


def to_radians_if_needed(pose: Sequence[float], degrees: bool) -> list[float]:
    out = [float(v) for v in pose]
    if degrees:
        out[3] = math.radians(out[3])
        out[4] = math.radians(out[4])
        out[5] = math.radians(out[5])
    return out


def to_meters_if_needed(pose: Sequence[float], mm: bool) -> list[float]:
    out = [float(v) for v in pose]
    if mm:
        out[0] /= 1000.0
        out[1] /= 1000.0
        out[2] /= 1000.0
    return out


def wrap_angle_rad(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def angular_delta_rad(src: float, dst: float) -> float:
    return wrap_angle_rad(dst - src)


def load_tcp_offset_yaml(path: Path) -> list[float]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if isinstance(data, dict):
        if "pose6" in data:
            data = data["pose6"]
        elif "tcp_offset_pose" in data:
            data = data["tcp_offset_pose"]
    if not isinstance(data, list) or len(data) != 6:
        raise ValueError(f"TCP offset file {path} must contain a 6-element list or pose6/tcp_offset_pose field")
    return [float(v) for v in data]


def main() -> int:
    args = parse_args()

    try:
        from pyAgxArm import AgxArmFactory, create_agx_arm_config
    except ImportError as exc:
        raise SystemExit(
            "pyAgxArm is not installed. Run: python3 -m pip install -e ./pyAgxArm"
        ) from exc

    target_pose_input = to_meters_if_needed(args.pose, args.mm)
    target_pose_input = to_radians_if_needed(target_pose_input, args.degrees)

    tcp_offset = None
    if args.tcp_offset is not None and args.tcp_offset_yaml:
        raise SystemExit("Pass only one of --tcp-offset or --tcp-offset-yaml.")
    if args.tcp_offset is not None:
        tcp_offset = to_meters_if_needed(args.tcp_offset, args.tcp_offset_mm)
        tcp_offset = to_radians_if_needed(tcp_offset, args.tcp_offset_degrees)
    elif args.tcp_offset_yaml:
        tcp_offset = load_tcp_offset_yaml(Path(args.tcp_offset_yaml))

    cfg = create_agx_arm_config(robot=args.robot, comm="can", channel=args.channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()

    if tcp_offset is not None:
        robot.set_tcp_offset(tcp_offset)
        print("TCP offset:", tcp_offset)

    status = robot.get_arm_status()
    if status is not None:
        print("Arm status:", status.msg)

    current_flange = robot.get_flange_pose()
    current_tcp = robot.get_tcp_pose() if hasattr(robot, "get_tcp_pose") else None
    target_flange_pose = target_pose_input
    target_tcp_pose = None

    if args.target_frame == "tcp":
        target_tcp_pose = target_pose_input
        if not hasattr(robot, "get_tcp2flange_pose"):
            raise SystemExit("Current pyAgxArm build does not support get_tcp2flange_pose().")
        target_flange_pose = [float(v) for v in robot.get_tcp2flange_pose(target_tcp_pose)]
    else:
        if current_flange is not None and hasattr(robot, "get_flange2tcp_pose"):
            target_tcp_pose = [float(v) for v in robot.get_flange2tcp_pose(target_flange_pose)]

    if current_flange is not None:
        print("Current flange_pose:", [float(v) for v in current_flange.msg])
    if current_tcp is not None:
        print("Current tcp_pose:", [float(v) for v in current_tcp.msg])
    print(f"Target  {args.target_frame}_pose:", target_pose_input)
    if args.target_frame == "tcp":
        print("Target  flange_pose:", target_flange_pose)
    elif target_tcp_pose is not None:
        print("Target  tcp_pose:", target_tcp_pose)
    print(f"Speed percent: {args.speed_percent}")
    if any(abs(v) > 5.0 for v in target_pose_input[:3]):
        print("Warning: x/y/z look large. Units are meters. If your UI shows mm, pass --mm.")
    if not check_pose_min_z(target_flange_pose, f"{args.target_frame}_pose"):
        print("Blocked by minimum z safety guard.")
        return 1

    if not args.go:
        print("Dry run: pass --go to send robot.enable()/robot.move_p().")
        return 0

    if not args.no_normal_mode and hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
        print("set_normal_mode sent.")

    if not args.no_enable:
        ok = robot.enable()
        print("enable (immediate):", ok)
        deadline = time.time() + max(0.0, args.enable_timeout)
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
        if last_states is not None:
            print("enabled joints:", last_states)
        else:
            print("enabled joints: (not available)")

    robot.set_speed_percent(args.speed_percent)
    def send_mode_p() -> None:
        for _ in range(max(1, args.mode_resend)):
            robot.set_motion_mode("p")
            time.sleep(0.02)

    if args.send_order == "sdk":
        robot.move_p(target_flange_pose)
        print("move_p sent (sdk).")
    else:
        if not hasattr(robot, "_deal_move_p_msgs") or not hasattr(robot, "_send_msgs"):
            raise SystemExit("send_order requires pyAgxArm Driver internals (_deal_move_p_msgs/_send_msgs).")
        msgs = robot._deal_move_p_msgs(target_flange_pose)
        if args.send_order == "target_then_mode":
            robot._send_msgs(msgs)
            send_mode_p()
        elif args.send_order == "mode_then_target":
            send_mode_p()
            robot._send_msgs(msgs)
        elif args.send_order == "mode_target_mode":
            send_mode_p()
            robot._send_msgs(msgs)
            send_mode_p()
        else:
            raise SystemExit(f"Unknown send_order: {args.send_order}")
        print(f"move_p sent ({args.send_order}).")

    status_after_send = robot.get_arm_status()
    if status_after_send is not None:
        print("Arm status after send:", status_after_send.msg)

    if args.sleep_after > 0:
        time.sleep(args.sleep_after)
    if args.wait_seconds > 0:
        start = time.time()
        base_msg = None
        if args.target_frame == "tcp" and current_tcp is not None:
            base_msg = current_tcp.msg
        elif args.target_frame == "flange" and current_flange is not None:
            base_msg = current_flange.msg
        last_pose = None
        last_status = None
        best_err_mm = None
        best_rot_deg = None
        while time.time() - start < args.wait_seconds:
            msg = robot.get_tcp_pose() if args.target_frame == "tcp" else robot.get_flange_pose()
            if msg is not None:
                last_pose = msg.msg
                if base_msg is not None:
                    dx = (last_pose[0] - base_msg[0]) * 1000.0
                    dy = (last_pose[1] - base_msg[1]) * 1000.0
                    dz = (last_pose[2] - base_msg[2]) * 1000.0
                    dist = (dx * dx + dy * dy + dz * dz) ** 0.5
                    if dist >= args.min_motion_mm:
                        print(f"Motion detected: {dist:.2f} mm")
                        # Don't break: motion-detected is informational.
                compare_target = target_pose_input
                dx_t = (last_pose[0] - compare_target[0]) * 1000.0
                dy_t = (last_pose[1] - compare_target[1]) * 1000.0
                dz_t = (last_pose[2] - compare_target[2]) * 1000.0
                err_mm = (dx_t * dx_t + dy_t * dy_t + dz_t * dz_t) ** 0.5
                rot_deg = max(abs(math.degrees(angular_delta_rad(last_pose[i], compare_target[i]))) for i in range(3, 6))
                if best_err_mm is None or err_mm < best_err_mm:
                    best_err_mm = err_mm
                if best_rot_deg is None or rot_deg < best_rot_deg:
                    best_rot_deg = rot_deg
                if err_mm <= max(0.0, args.tolerance_mm) and rot_deg <= max(0.0, args.tolerance_deg):
                    print(f"Reached target: translation={err_mm:.2f} mm rotation={rot_deg:.2f} deg")
                    break
            st = robot.get_arm_status()
            if st is not None:
                last_status = st.msg
            time.sleep(0.05)
        if last_pose is not None:
            print(f"Last {args.target_frame}_pose:", [float(v) for v in last_pose])
            dx_t = (last_pose[0] - target_pose_input[0]) * 1000.0
            dy_t = (last_pose[1] - target_pose_input[1]) * 1000.0
            dz_t = (last_pose[2] - target_pose_input[2]) * 1000.0
            err_mm = (dx_t * dx_t + dy_t * dy_t + dz_t * dz_t) ** 0.5
            rot_deg = max(abs(math.degrees(angular_delta_rad(last_pose[i], target_pose_input[i]))) for i in range(3, 6))
            best_err_str = "n/a" if best_err_mm is None else f"{best_err_mm:.2f}"
            best_rot_str = "n/a" if best_rot_deg is None else f"{best_rot_deg:.2f}"
            print(f"Final translation error: {err_mm:.2f} mm (best {best_err_str} mm)")
            print(f"Final rotation error: {rot_deg:.2f} deg (best {best_rot_str} deg)")
        else:
            print(f"Last {args.target_frame}_pose: (not available)")
        if last_status is not None:
            print("Last arm_status:", last_status)

    return 0


if __name__ == "__main__":
    sys.exit(main())
