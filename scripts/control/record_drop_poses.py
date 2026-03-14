#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm

prefer_local_pyagxarm(__file__)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "drop_poses.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record current robot XY drop/recycle positions."
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel, e.g. can0")
    parser.add_argument("--robot", default="nero", help="Robot name passed into pyAgxArm (default: nero)")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="YAML file used to store named drop poses.",
    )
    parser.add_argument(
        "--record",
        default="",
        help="Name of the drop position to record, e.g. bottle or cup.",
    )
    parser.add_argument(
        "--frame",
        choices=["flange"],
        default="flange",
        help="Reference frame to store. First version only supports flange XY.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show currently saved drop positions and exit.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Overwrite an existing pose without asking.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait for a valid current pose. Default: 2.0.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {"drop_poses": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config file must contain a YAML mapping: {path}")
    drop_poses = data.get("drop_poses")
    if drop_poses is None:
        data["drop_poses"] = {}
    elif not isinstance(drop_poses, dict):
        raise SystemExit(f"'drop_poses' must be a YAML mapping: {path}")
    return data


def save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def format_xy(xy: list[float]) -> str:
    xy_mm = [round(v * 1000.0, 3) for v in xy[:2]]
    return f"m={xy}\nmm={xy_mm}"


def read_flange_pose(robot: object, timeout_s: float) -> list[float] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = robot.get_flange_pose()
        if msg is not None:
            return [float(v) for v in msg.msg]
        time.sleep(0.05)
    return None


def prompt_overwrite(name: str, current_entry: dict) -> bool:
    print(f"Drop position '{name}' already exists.")
    existing_xy = current_entry.get("xy")
    if isinstance(existing_xy, list) and len(existing_xy) == 2:
        print("Existing XY:")
        print(format_xy([float(v) for v in existing_xy]))
    answer = input("Overwrite it? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def print_saved_poses(path: Path, data: dict) -> None:
    print(f"Config: {path}")
    drop_poses = data.get("drop_poses", {})
    if not drop_poses:
        print("No saved drop poses.")
        return
    for name, entry in drop_poses.items():
        print(f"\n[{name}]")
        if not isinstance(entry, dict):
            print(entry)
            continue
        xy = entry.get("xy")
        if isinstance(xy, list) and len(xy) == 2:
            print(format_xy([float(v) for v in xy]))
        else:
            print(f"xy={xy}")
        for key in ["frame", "updated_at", "channel", "robot"]:
            if key in entry:
                print(f"{key}={entry[key]}")


def build_robot(channel: str, robot_name: str):
    from pyAgxArm import AgxArmFactory, create_agx_arm_config

    cfg = create_agx_arm_config(robot=robot_name, comm="can", channel=channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    return robot


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    data = load_yaml(config_path)

    if args.show and not args.record:
        print_saved_poses(config_path, data)
        return 0

    pose_name = args.record.strip()
    if not pose_name:
        raise SystemExit("Pass --record <name> to save a drop pose, or use --show to inspect saved poses.")

    robot = build_robot(args.channel, args.robot)
    current_pose = read_flange_pose(robot, timeout_s=max(0.1, args.read_timeout))
    if current_pose is None:
        raise SystemExit("Failed to read current flange pose from the robot.")
    current_xy = [float(current_pose[0]), float(current_pose[1])]

    print(f"Current {args.frame} XY for '{pose_name}':")
    print(format_xy(current_xy))

    drop_poses = data.setdefault("drop_poses", {})
    existing = drop_poses.get(pose_name)
    if existing is not None and not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit(
                f"Drop position '{pose_name}' already exists. Re-run with --yes to overwrite non-interactively."
            )
        if not prompt_overwrite(pose_name, existing):
            print("Aborted. Existing drop position kept unchanged.")
            return 0

    drop_poses[pose_name] = {
        "xy": [float(v) for v in current_xy],
        "frame": args.frame,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "channel": args.channel,
        "robot": args.robot,
    }
    save_yaml(config_path, data)

    print(f"Saved drop position '{pose_name}' to {config_path}")
    print_saved_poses(config_path, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
