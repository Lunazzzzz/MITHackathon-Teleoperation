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


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "task_poses.yaml"
DEFAULT_POSE_NAMES = ["home", "work", "standby"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record current robot flange poses for workflow task poses such as home/work/standby."
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel, e.g. can0")
    parser.add_argument("--robot", default="nero", help="Robot name passed into pyAgxArm (default: nero)")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="YAML file used to store named task poses.",
    )
    parser.add_argument(
        "--record",
        default="",
        help="Name of the task pose to record, e.g. home, work, standby.",
    )
    parser.add_argument(
        "--frame",
        choices=["flange"],
        default="flange",
        help="Pose frame to store. First version only supports flange.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show currently saved task poses and exit.",
    )
    parser.add_argument(
        "--init-defaults",
        action="store_true",
        help="Ensure home/work/standby keys exist in the config and print the current file.",
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
        return {
            "task_poses": {},
            "workflow_notes": {
                "pick_path": ["home", "work", "target_hover", "pregrasp_10cm", "grasp"],
                "place_path": ["grasp_retreat", "standby", "drop_hover", "drop_down", "release"],
            },
        }
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config file must contain a YAML mapping: {path}")
    task_poses = data.get("task_poses")
    if task_poses is None:
        data["task_poses"] = {}
    elif not isinstance(task_poses, dict):
        raise SystemExit(f"'task_poses' must be a YAML mapping: {path}")
    if "workflow_notes" not in data:
        data["workflow_notes"] = {
            "pick_path": ["home", "work", "target_hover", "pregrasp_10cm", "grasp"],
            "place_path": ["grasp_retreat", "standby", "drop_hover", "drop_down", "release"],
        }
    return data


def save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def ensure_default_keys(data: dict) -> None:
    task_poses = data.setdefault("task_poses", {})
    for name in DEFAULT_POSE_NAMES:
        task_poses.setdefault(name, None)


def format_pose(pose: list[float]) -> str:
    xyz_mm = [round(v * 1000.0, 3) for v in pose[:3]]
    rpy_deg = [round(v * 180.0 / 3.141592653589793, 3) for v in pose[3:]]
    return (
        f"m/rad={pose}\n"
        f"mm/deg={[xyz_mm[0], xyz_mm[1], xyz_mm[2], rpy_deg[0], rpy_deg[1], rpy_deg[2]]}"
    )


def read_flange_pose(robot: object, timeout_s: float) -> list[float] | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = robot.get_flange_pose()
        if msg is not None:
            return [float(v) for v in msg.msg]
        time.sleep(0.05)
    return None


def prompt_overwrite(name: str, current_entry: dict | None) -> bool:
    print(f"Task pose '{name}' already exists.")
    if isinstance(current_entry, dict):
        existing_pose = current_entry.get("pose")
        if isinstance(existing_pose, list) and len(existing_pose) == 6:
            print("Existing pose:")
            print(format_pose([float(v) for v in existing_pose]))
    answer = input("Overwrite it? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def print_saved_poses(path: Path, data: dict) -> None:
    print(f"Config: {path}")
    task_poses = data.get("task_poses", {})
    if not task_poses:
        print("No saved task poses.")
    else:
        for name, entry in task_poses.items():
            print(f"\n[{name}]")
            if entry is None:
                print("unset")
                continue
            if not isinstance(entry, dict):
                print(entry)
                continue
            pose = entry.get("pose")
            if isinstance(pose, list) and len(pose) == 6:
                print(format_pose([float(v) for v in pose]))
            else:
                print(f"pose={pose}")
            for key in ["frame", "updated_at", "channel", "robot"]:
                if key in entry:
                    print(f"{key}={entry[key]}")
    workflow_notes = data.get("workflow_notes")
    if isinstance(workflow_notes, dict):
        print("\nworkflow_notes:")
        print(yaml.safe_dump(workflow_notes, sort_keys=False, allow_unicode=True).strip())


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
    ensure_default_keys(data)

    if args.init_defaults:
        save_yaml(config_path, data)
        print_saved_poses(config_path, data)
        return 0

    if args.show and not args.record:
        print_saved_poses(config_path, data)
        return 0

    pose_name = args.record.strip()
    if not pose_name:
        raise SystemExit("Pass --record <name> to save a task pose, or use --show/--init-defaults.")

    robot = build_robot(args.channel, args.robot)
    current_pose = read_flange_pose(robot, timeout_s=max(0.1, args.read_timeout))
    if current_pose is None:
        raise SystemExit("Failed to read current flange pose from the robot.")

    print(f"Current {args.frame} pose for '{pose_name}':")
    print(format_pose(current_pose))

    task_poses = data.setdefault("task_poses", {})
    existing = task_poses.get(pose_name)
    if existing is not None and not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit(
                f"Task pose '{pose_name}' already exists. Re-run with --yes to overwrite non-interactively."
            )
        if not prompt_overwrite(pose_name, existing if isinstance(existing, dict) else None):
            print("Aborted. Existing task pose kept unchanged.")
            return 0

    task_poses[pose_name] = {
        "pose": [float(v) for v in current_pose],
        "frame": args.frame,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "channel": args.channel,
        "robot": args.robot,
    }
    save_yaml(config_path, data)

    print(f"Saved task pose '{pose_name}' to {config_path}")
    print_saved_poses(config_path, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
