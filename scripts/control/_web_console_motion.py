#!/usr/bin/env python3
from __future__ import annotations

import math
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from typing import Any, Callable

import numpy as np
import pyrealsense2 as rs
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _safety import MIN_TOOL_Z_M, check_pose_min_z
from omnihand_actions import OmniHandActions
from run_fake_grasp_cycle import (
    build_cycle_poses as build_cycle_poses_from_script,
    build_robot as build_robot_from_script,
    choose_target as choose_target_from_script,
    format_target_label,
    load_task_pose as load_task_pose_from_script,
    pose_close_enough as pose_close_enough_from_script,
    prepare_robot as prepare_robot_from_script,
    read_flange_pose as read_flange_pose_from_script,
    send_pose as send_pose_from_script,
)

TASK_POSE_NAMES = ("home", "work", "standby")
DROP_POSE_NAMES = ("bottle", "cup")
REACHABILITY_TRANSLATION_TOL_MM = 50.0
REACHABILITY_ROTATION_TOL_DEG = 25.0
REACHABILITY_WAIT_SECONDS = 2.0


class WebConsoleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class WorkflowStopped(RuntimeError):
    pass


def wrap_angle_rad(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    return angle


def angular_delta_rad(src: float, dst: float) -> float:
    return wrap_angle_rad(dst - src)


def monitor_pose_reached(
    robot: object,
    target_pose: list[float],
    *,
    wait_seconds: float = REACHABILITY_WAIT_SECONDS,
    tolerance_mm: float = REACHABILITY_TRANSLATION_TOL_MM,
    tolerance_deg: float = REACHABILITY_ROTATION_TOL_DEG,
) -> dict[str, float | bool | list[float] | None]:
    best_translation_mm = None
    best_rotation_deg = None
    last_pose = None

    start = time.time()
    while time.time() - start < max(0.1, wait_seconds):
        pose_msg = robot.get_flange_pose()
        if pose_msg is not None:
            last_pose = [float(v) for v in pose_msg.msg]
            translation_err_mm = math.sqrt(sum(((last_pose[i] - target_pose[i]) * 1000.0) ** 2 for i in range(3)))
            rotation_err_deg = max(abs(math.degrees(angular_delta_rad(last_pose[i], target_pose[i]))) for i in range(3, 6))
            if best_translation_mm is None or translation_err_mm < best_translation_mm:
                best_translation_mm = translation_err_mm
            if best_rotation_deg is None or rotation_err_deg < best_rotation_deg:
                best_rotation_deg = rotation_err_deg
            if translation_err_mm <= tolerance_mm and rotation_err_deg <= tolerance_deg:
                return {
                    "success": True,
                    "last_pose": last_pose,
                    "best_translation_err_mm": best_translation_mm,
                    "best_rotation_err_deg": best_rotation_deg,
                }
        time.sleep(0.05)

    return {
        "success": False,
        "last_pose": last_pose,
        "best_translation_err_mm": best_translation_mm,
        "best_rotation_err_deg": best_rotation_deg,
    }


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise WebConsoleError("UNKNOWN_ERROR", f"YAML root must be a mapping: {path}")
    return data


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def serialize_task_poses(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    task_poses = data.get("task_poses", {})
    response: dict[str, Any] = {"task_poses": {}}
    if not isinstance(task_poses, dict):
        return response
    for name in TASK_POSE_NAMES:
        entry = task_poses.get(name)
        if not isinstance(entry, dict):
            continue
        pose = entry.get("pose")
        if not isinstance(pose, list) or len(pose) != 6:
            continue
        response["task_poses"][name] = {
            "pose": [float(v) for v in pose],
            "frame": entry.get("frame"),
            "updated_at": entry.get("updated_at"),
        }
    return response


def serialize_drop_poses(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    drop_poses = data.get("drop_poses", {})
    response: dict[str, Any] = {"drop_poses": {}}
    if not isinstance(drop_poses, dict):
        return response
    for name in DROP_POSE_NAMES:
        entry = drop_poses.get(name)
        if not isinstance(entry, dict):
            continue
        xy = entry.get("xy")
        if not isinstance(xy, list) or len(xy) != 2:
            pose = entry.get("pose")
            if isinstance(pose, list) and len(pose) >= 2:
                xy = [float(pose[0]), float(pose[1])]
        if not isinstance(xy, list) or len(xy) != 2:
            continue
        response["drop_poses"][name] = {
            "xy": [float(v) for v in xy],
            "frame": entry.get("frame"),
            "updated_at": entry.get("updated_at"),
        }
    return response


def build_robot(channel: str, robot_name: str):
    return build_robot_from_script(channel, robot_name)


def prepare_robot(robot: object, speed_percent: int) -> None:
    prepare_robot_from_script(robot, speed_percent)


def read_flange_pose(robot: object, timeout_s: float = 2.0) -> list[float] | None:
    return read_flange_pose_from_script(robot, timeout_s=timeout_s)


def pose_close_enough(current_pose: list[float] | None, target_pose: list[float]) -> bool:
    return pose_close_enough_from_script(current_pose, target_pose)


def choose_target(
    raw_rows: list[dict[str, object]],
    depth_frame: rs.depth_frame,
    intrinsics: rs.intrinsics,
    base_to_camera: np.ndarray,
    *,
    target_labels: list[str],
    depth_window: int,
) -> dict[str, object] | None:
    return choose_target_from_script(
        raw_rows,
        depth_frame,
        intrinsics,
        base_to_camera,
        target_labels=target_labels,
        depth_window=depth_window,
    )


def _build_cycle_namespace(runtime_config: Any, drop_poses_file: str) -> Any:
    return SimpleNamespace(
        hover_height_m=runtime_config.hover_height_m,
        grasp_z_offset_m=runtime_config.grasp_z_offset_m,
        drop_hover_offset_m=0.10,
        drop_hover_z_m=runtime_config.drop_hover_z_m,
        drop_z_m=runtime_config.drop_z_m,
        grasp_offset_m=list(runtime_config.base_offset_m),
        pose_rpy_deg=list(runtime_config.pose_rpy_deg),
        grasp_rpy_deg=list(runtime_config.pose_rpy_deg),
        drop_poses_file=drop_poses_file,
    )


def build_cycle_poses(best: dict[str, object], runtime_config: Any, drop_poses_file: str) -> dict[str, list[float]]:
    try:
        return build_cycle_poses_from_script(best, _build_cycle_namespace(runtime_config, drop_poses_file))
    except SystemExit as exc:
        raise WebConsoleError("MISSING_DROP_POSE", str(exc)) from exc


def load_task_pose(path: str, name: str) -> list[float]:
    try:
        return load_task_pose_from_script(path, name)
    except SystemExit as exc:
        raise WebConsoleError("MISSING_TASK_POSE", str(exc)) from exc


def _ensure_safe_pose(label: str, pose: list[float]) -> None:
    if not check_pose_min_z(pose, label, min_z_m=MIN_TOOL_Z_M):
        raise WebConsoleError("MIN_Z_BLOCKED", f"Blocked by minimum z safety guard at {label}.")


def _send_pose(robot: object, pose: list[float], send_order: str, mode_resend: int) -> None:
    try:
        send_pose_from_script(robot, pose, send_order, mode_resend)
    except RuntimeError as exc:
        raise WebConsoleError("UNKNOWN_ERROR", str(exc)) from exc


def move_pose(
    robot: object | None,
    pose: list[float],
    *,
    execute: bool,
    label: str,
    settle_seconds: float,
    send_order: str,
    mode_resend: int,
    verify_reached: bool = False,
    step_callback: Callable[[str], None] | None = None,
    stop_event: Event | None = None,
) -> None:
    if stop_event is not None and stop_event.is_set():
        raise WorkflowStopped()
    if step_callback is not None:
        step_callback(label)
    _ensure_safe_pose(label, pose)
    if execute and robot is not None:
        _send_pose(robot, pose, send_order, mode_resend)
        time.sleep(max(0.0, settle_seconds))
        if verify_reached:
            monitor = monitor_pose_reached(robot, pose)
            if not bool(monitor["success"]):
                translation_text = (
                    "n/a"
                    if monitor["best_translation_err_mm"] is None
                    else f"{float(monitor['best_translation_err_mm']):.1f} mm"
                )
                rotation_text = (
                    "n/a"
                    if monitor["best_rotation_err_deg"] is None
                    else f"{float(monitor['best_rotation_err_deg']):.1f} deg"
                )
                raise WebConsoleError(
                    "UNREACHABLE_TARGET",
                    f"{label} 不可达，请重新识别/重试抓取。最佳误差: {translation_text}, {rotation_text}",
                )
    if stop_event is not None and stop_event.is_set():
        raise WorkflowStopped()


def act_hand(
    hand: OmniHandActions | None,
    *,
    action: str,
    execute: bool,
    settle_seconds: float,
    step_callback: Callable[[str], None] | None = None,
    step_label: str | None = None,
    stop_event: Event | None = None,
) -> None:
    if stop_event is not None and stop_event.is_set():
        raise WorkflowStopped()
    if step_label is not None and step_callback is not None:
        step_callback(step_label)
    if hand is None:
        return
    if action == "open":
        hand.open_hand()
    elif action == "close":
        hand.close_hand()
    else:
        raise WebConsoleError("UNKNOWN_ERROR", f"Unsupported hand action: {action}")
    if execute:
        time.sleep(max(0.0, settle_seconds))
    if stop_event is not None and stop_event.is_set():
        raise WorkflowStopped()


def move_named_pose(
    robot: object,
    *,
    task_poses_file: str,
    name: str,
    settle_seconds: float,
    send_order: str,
    mode_resend: int,
    step_callback: Callable[[str], None] | None = None,
) -> list[float]:
    pose = load_task_pose(task_poses_file, name)
    move_pose(
        robot,
        pose,
        execute=True,
        label=name,
        settle_seconds=settle_seconds,
        send_order=send_order,
        mode_resend=mode_resend,
        step_callback=step_callback,
    )
    return pose


def execute_fake_cycle(
    robot: object,
    hand: OmniHandActions | None,
    *,
    task_poses_file: str,
    cycle_poses: dict[str, list[float]],
    settle_seconds: float,
    send_order: str,
    mode_resend: int,
    step_callback: Callable[[str], None] | None = None,
    stop_event: Event | None = None,
) -> None:
    home_pose = load_task_pose(task_poses_file, "home")
    work_pose = load_task_pose(task_poses_file, "work")
    standby_pose = load_task_pose(task_poses_file, "standby")

    move_pose(robot, home_pose, execute=True, label="home", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    move_pose(robot, work_pose, execute=True, label="work", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    act_hand(hand, action="open", execute=True, settle_seconds=settle_seconds, stop_event=stop_event)
    move_pose(robot, cycle_poses["target_hover"], execute=True, label="target_hover", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, verify_reached=True, step_callback=step_callback, stop_event=stop_event)
    move_pose(robot, cycle_poses["pregrasp_10cm"], execute=True, label="pregrasp_10cm", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, verify_reached=True, step_callback=step_callback, stop_event=stop_event)
    act_hand(hand, action="close", execute=True, settle_seconds=settle_seconds, step_callback=step_callback, step_label="[FAKE GRASP]", stop_event=stop_event)
    move_pose(robot, cycle_poses["target_retreat"], execute=True, label="target_retreat", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    move_pose(robot, standby_pose, execute=True, label="standby", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    move_pose(robot, cycle_poses["drop_hover"], execute=True, label="drop_hover", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    move_pose(robot, cycle_poses["drop_down"], execute=True, label="drop_down", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    act_hand(hand, action="open", execute=True, settle_seconds=settle_seconds, step_callback=step_callback, step_label="[FAKE RELEASE]", stop_event=stop_event)
    move_pose(robot, cycle_poses["drop_retreat"], execute=True, label="drop_retreat", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)
    move_pose(robot, home_pose, execute=True, label="return_home", settle_seconds=settle_seconds, send_order=send_order, mode_resend=mode_resend, step_callback=step_callback, stop_event=stop_event)


def record_task_pose(
    robot: object,
    *,
    config_path: Path,
    name: str,
    channel: str,
    robot_name: str,
    overwrite: bool,
    read_timeout: float = 2.0,
) -> dict[str, Any]:
    data = load_yaml(config_path)
    task_poses = data.setdefault("task_poses", {})
    if not isinstance(task_poses, dict):
        raise WebConsoleError("UNKNOWN_ERROR", f"'task_poses' must be a mapping: {config_path}")
    if task_poses.get(name) is not None and not overwrite:
        raise WebConsoleError("UNKNOWN_ERROR", f"Task pose '{name}' already exists.")
    current_pose = read_flange_pose(robot, timeout_s=max(0.1, read_timeout))
    if current_pose is None:
        raise WebConsoleError("UNKNOWN_ERROR", "Failed to read current flange pose from the robot.")
    task_poses[name] = {
        "pose": [float(v) for v in current_pose],
        "frame": "flange",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "channel": channel,
        "robot": robot_name,
    }
    save_yaml(config_path, data)
    return serialize_task_poses(config_path)


def record_drop_pose(
    robot: object,
    *,
    config_path: Path,
    name: str,
    channel: str,
    robot_name: str,
    overwrite: bool,
    read_timeout: float = 2.0,
) -> dict[str, Any]:
    data = load_yaml(config_path)
    drop_poses = data.setdefault("drop_poses", {})
    if not isinstance(drop_poses, dict):
        raise WebConsoleError("UNKNOWN_ERROR", f"'drop_poses' must be a mapping: {config_path}")
    if drop_poses.get(name) is not None and not overwrite:
        raise WebConsoleError("UNKNOWN_ERROR", f"Drop pose '{name}' already exists.")
    current_pose = read_flange_pose(robot, timeout_s=max(0.1, read_timeout))
    if current_pose is None:
        raise WebConsoleError("UNKNOWN_ERROR", "Failed to read current flange pose from the robot.")
    current_pose = [float(v) for v in current_pose]
    current_xy = [float(current_pose[0]), float(current_pose[1])]
    drop_poses[name] = {
        "pose": current_pose,
        "xy": current_xy,
        "frame": "flange",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "channel": channel,
        "robot": robot_name,
    }
    save_yaml(config_path, data)
    return serialize_drop_poses(config_path)
