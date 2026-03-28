#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
import yaml
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
VISION_DIR = SCRIPTS_DIR / "vision"
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(VISION_DIR) not in sys.path:
    sys.path.insert(0, str(VISION_DIR))

from _local_sdk import prefer_local_pyagxarm
from _local_ultralytics import maybe_enable_binaryattention
from omnihand_actions import create_actions
from trash_labels import DEFAULT_ACTIVE_TARGET_LABELS, normalize_requested_target_labels, resolve_target_name
from _common import (
    build_pipeline,
    default_model_path,
    intrinsics_from_profile,
    normalize_rotate_inference_modes,
    predict_detection_rows_multirotation,
    resolve_device,
    resolve_path,
)

from _web_console_motion import (
    WebConsoleError,
    WorkflowStopped,
    build_cycle_poses,
    build_robot,
    choose_target,
    execute_fake_cycle,
    format_target_label,
    move_named_pose,
    pose_close_enough,
    prepare_robot,
    read_flange_pose,
    record_drop_pose,
    record_task_pose,
    serialize_drop_poses,
    serialize_task_poses,
)
from run_fake_grasp_cycle import load_base_to_camera

prefer_local_pyagxarm(__file__)


DEFAULT_TASK_POSES_PATH = REPO_ROOT / "config" / "task_poses.yaml"
DEFAULT_DROP_POSES_PATH = REPO_ROOT / "config" / "drop_poses.yaml"
DEFAULT_HAND_CONFIG_PATH = REPO_ROOT / "config" / "sort_trash_pipeline.example.yaml"
DEFAULT_RUNTIME_CONFIG_PATH = REPO_ROOT / "config" / "web_runtime_config.yaml"

CAPABILITIES = {
    "fake_grasp": True,
    "follow": False,
    "video": True,
    "pose_recording": True,
}


@dataclass
class RuntimeConfig:
    hover_height_m: float = 0.15
    grasp_z_offset_m: float = 0.10
    drop_hover_z_m: float = 0.25
    drop_z_m: float = 0.15
    follow_rate_hz: float = 10.0
    imgsz: int = 960
    base_offset_m: tuple[float, float, float] = (0.13, 0.0, 0.0)
    pose_rpy_deg: tuple[float, float, float] = (90.10, -3.89, -1.41)
    rotate_inference_modes: list[str] = field(default_factory=lambda: ["none", "cw90", "ccw90"])
    target_labels: list[str] = field(default_factory=lambda: ["bottle", "cup"])

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "RuntimeConfig":
        defaults = cls()
        target_labels = normalize_requested_target_labels(
            data.get("target_labels", defaults.target_labels),
            default=defaults.target_labels,
        )
        rotate_inference_modes = normalize_rotate_inference_modes(
            "none",
            data.get("rotate_inference_modes", defaults.rotate_inference_modes),
        )
        return cls(
            hover_height_m=float(data.get("hover_height_m", defaults.hover_height_m)),
            grasp_z_offset_m=float(data.get("grasp_z_offset_m", defaults.grasp_z_offset_m)),
            drop_hover_z_m=float(data.get("drop_hover_z_m", defaults.drop_hover_z_m)),
            drop_z_m=float(data.get("drop_z_m", defaults.drop_z_m)),
            follow_rate_hz=float(data.get("follow_rate_hz", defaults.follow_rate_hz)),
            imgsz=int(data.get("imgsz", defaults.imgsz)),
            base_offset_m=tuple(float(v) for v in data.get("base_offset_m", defaults.base_offset_m)),
            pose_rpy_deg=tuple(float(v) for v in data.get("pose_rpy_deg", defaults.pose_rpy_deg)),
            rotate_inference_modes=list(rotate_inference_modes),
            target_labels=target_labels,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hover_height_m": float(self.hover_height_m),
            "grasp_z_offset_m": float(self.grasp_z_offset_m),
            "drop_hover_z_m": float(self.drop_hover_z_m),
            "drop_z_m": float(self.drop_z_m),
            "follow_rate_hz": float(self.follow_rate_hz),
            "imgsz": int(self.imgsz),
            "base_offset_m": [float(v) for v in self.base_offset_m],
            "pose_rpy_deg": [float(v) for v in self.pose_rpy_deg],
            "rotate_inference_modes": list(self.rotate_inference_modes),
            "target_labels": list(self.target_labels),
        }

    def to_cycle_args(self, *, drop_poses_file: str) -> Any:
        return SimpleNamespace(
            hover_height_m=float(self.hover_height_m),
            grasp_z_offset_m=float(self.grasp_z_offset_m),
            drop_hover_offset_m=0.10,
            drop_hover_z_m=float(self.drop_hover_z_m),
            drop_z_m=float(self.drop_z_m),
            grasp_offset_m=[float(v) for v in self.base_offset_m],
            pose_rpy_deg=[float(v) for v in self.pose_rpy_deg],
            grasp_rpy_deg=[float(v) for v in self.pose_rpy_deg],
            drop_poses_file=drop_poses_file,
        )


def _load_runtime_config(path: Path) -> RuntimeConfig:
    if not path.exists():
        cfg = RuntimeConfig()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(cfg.to_dict(), handle, sort_keys=False, allow_unicode=True)
        return cfg
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise WebConsoleError("UNKNOWN_ERROR", f"Runtime config root must be a mapping: {path}")
    return RuntimeConfig.from_mapping(data)


def _save_runtime_config(path: Path, config: RuntimeConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config.to_dict(), handle, sort_keys=False, allow_unicode=True)


def _build_placeholder_frame(text: str) -> bytes:
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    canvas[:] = (2, 6, 23)
    cv2.putText(canvas, "NERO WEB CONSOLE", (70, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (103, 232, 249), 3)
    cv2.putText(canvas, text, (70, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (226, 232, 240), 2)
    ok, encoded = cv2.imencode(".jpg", canvas)
    return encoded.tobytes() if ok else b""


def _can_interface_up(channel: str) -> bool:
    result = subprocess.run(
        ["ip", "-details", "link", "show", channel],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return "state UP" in result.stdout


class WebConsoleRuntime:
    def __init__(self, args: Any):
        self.args = args
        self.model_path = resolve_path(args.model)
        self.calibration_path, self.base_to_camera = load_base_to_camera(args.calibration_file)
        self.task_poses_file = Path(args.task_poses_file).expanduser().resolve()
        self.drop_poses_file = Path(args.drop_poses_file).expanduser().resolve()
        self.hand_config = str(Path(args.hand_config).expanduser().resolve())
        self.runtime_config_path = Path(args.runtime_config_file).expanduser().resolve()
        self.runtime_config = _load_runtime_config(self.runtime_config_path)
        self.device = resolve_device(args.device, args.allow_cpu)

        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._stop_task_event = threading.Event()
        self._vision_thread: threading.Thread | None = None
        self._task_thread: threading.Thread | None = None

        self.pipeline = None
        self.align = None
        self.profile = None
        self.intrinsics = None
        self.model = None
        self.robot = None
        self.hand = None

        self.can_up = _can_interface_up(self.args.channel)
        self.robot_connected = False
        self.camera_ready = False
        self.model_ready = False
        self.busy = False
        self.current_mode = "idle"
        self.current_step: str | None = None
        self.last_issue: dict[str, str] | None = None
        self.last_unreachable_target: dict[str, Any] | None = None

        self.latest_best: dict[str, object] | None = None
        self.latest_detection_state: dict[str, Any] = {"target": None, "top_detections": []}
        self.latest_frame_jpeg = _build_placeholder_frame("Starting backend...")

    def startup(self) -> None:
        self._start_model()
        self._start_camera()
        self._connect_robot()
        self._connect_hand()
        if self.camera_ready and self.model_ready and self._vision_thread is None:
            self._vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
            self._vision_thread.start()
            self.current_mode = "detecting"

    def shutdown(self) -> None:
        self._shutdown_event.set()
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass
        if self._vision_thread is not None:
            self._vision_thread.join(timeout=1.0)

    def _start_model(self) -> None:
        try:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Model file does not exist: {self.model_path}")
            maybe_enable_binaryattention(__file__, self.model_path, verbose=False)
            self.model = YOLO(str(self.model_path))
            self.model_ready = True
        except Exception as exc:
            self.model_ready = False
            self.latest_frame_jpeg = _build_placeholder_frame(f"Model load failed: {exc}")

    def _start_camera(self) -> None:
        try:
            self.pipeline, self.align, self.profile = build_pipeline(
                camera_serial=self.args.camera_serial,
                width=self.args.width,
                height=self.args.height,
                fps=self.args.fps,
                enable_depth=True,
            )
            self.intrinsics = intrinsics_from_profile(self.profile)
            self.camera_ready = True
        except Exception as exc:
            self.camera_ready = False
            self.latest_frame_jpeg = _build_placeholder_frame(f"Camera init failed: {exc}")

    def _connect_robot(self) -> object | None:
        self.can_up = _can_interface_up(self.args.channel)
        if self.robot is not None:
            self.robot_connected = True
            return self.robot
        if not self.can_up:
            self.robot_connected = False
            return None
        try:
            self.robot = build_robot(self.args.channel, self.args.robot)
            prepare_robot(self.robot, self.args.speed_percent)
            self.robot_connected = True
            return self.robot
        except Exception:
            self.robot = None
            self.robot_connected = False
            return None

    def _connect_hand(self) -> None:
        if self.hand is not None:
            return
        try:
            self.hand = create_actions(self.hand_config, execute=True)
        except Exception:
            self.hand = None

    def ensure_robot(self) -> object:
        robot = self._connect_robot()
        if robot is None:
            raise WebConsoleError("CAN_DOWN", f"CAN port {self.args.channel} is not available.")
        return robot

    def get_status(self) -> dict[str, Any]:
        self.can_up = _can_interface_up(self.args.channel)
        if not self.busy and self.camera_ready and self.model_ready:
            self.current_mode = "detecting"
        return {
            "can_up": bool(self.can_up),
            "robot_connected": bool(self.robot_connected),
            "camera_ready": bool(self.camera_ready),
            "model_ready": bool(self.model_ready),
            "busy": bool(self.busy),
            "current_mode": self.current_mode,
            "current_step": self.current_step,
            "calibration_file": str(self.calibration_path),
            "safety": {"min_z_m": 0.10},
            "capabilities": dict(CAPABILITIES),
            "last_issue": dict(self.last_issue) if self.last_issue is not None else None,
        }

    def get_detection_state(self) -> dict[str, Any]:
        with self._lock:
            state = json.loads(json.dumps(self.latest_detection_state))
            if self.last_issue is not None and self.last_issue.get("code") == "UNREACHABLE_TARGET":
                if self._same_target(self.latest_best, self.last_unreachable_target):
                    state["reachability_issue"] = dict(self.last_issue)
            return state

    def get_runtime_config(self) -> dict[str, Any]:
        with self._lock:
            return self.runtime_config.to_dict()

    def update_runtime_config(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            merged = {**self.runtime_config.to_dict(), **data}
            self.runtime_config = RuntimeConfig.from_mapping(merged)
            _save_runtime_config(self.runtime_config_path, self.runtime_config)
            return self.runtime_config.to_dict()

    def get_task_poses(self) -> dict[str, Any]:
        return serialize_task_poses(self.task_poses_file)

    def get_drop_poses(self) -> dict[str, Any]:
        return serialize_drop_poses(self.drop_poses_file)

    def record_task_pose(self, name: str, overwrite: bool) -> dict[str, Any]:
        robot = self.ensure_robot()
        return record_task_pose(
            robot,
            config_path=self.task_poses_file,
            name=name,
            channel=self.args.channel,
            robot_name=self.args.robot,
            overwrite=overwrite,
        )

    def record_drop_pose(self, name: str, overwrite: bool) -> dict[str, Any]:
        robot = self.ensure_robot()
        return record_drop_pose(
            robot,
            config_path=self.drop_poses_file,
            name=name,
            channel=self.args.channel,
            robot_name=self.args.robot,
            overwrite=overwrite,
        )

    def move_named_pose(self, name: str) -> None:
        if self.busy:
            raise WebConsoleError("BUSY", "Another workflow is already running.")
        robot = self.ensure_robot()
        self.current_step = name
        move_named_pose(
            robot,
            task_poses_file=str(self.task_poses_file),
            name=name,
            settle_seconds=self.args.settle_seconds,
            send_order=self.args.send_order,
            mode_resend=self.args.mode_resend,
        )
        self.current_mode = "detecting" if self.camera_ready else "idle"

    def start_fake_grasp(self) -> None:
        with self._lock:
            if self.busy:
                raise WebConsoleError("BUSY", "Another workflow is already running.")
            if self.latest_best is None:
                raise WebConsoleError("UNKNOWN_ERROR", "No valid target")
            best = json.loads(json.dumps(self.latest_best))
            config = dataclasses.replace(self.runtime_config)
            self.last_issue = None
            self.busy = True
            self.current_mode = "running_fake_cycle"
            self.current_step = None
            self._stop_task_event.clear()
        self._task_thread = threading.Thread(
            target=self._run_fake_grasp_thread,
            args=(best, config),
            daemon=True,
        )
        self._task_thread.start()

    def stop_workflow(self) -> None:
        self._stop_task_event.set()

    def _run_fake_grasp_thread(self, best: dict[str, Any], runtime_config: RuntimeConfig) -> None:
        try:
            robot = self.ensure_robot()
            self._connect_hand()
            cycle_poses = build_cycle_poses(best, runtime_config, str(self.drop_poses_file))
            execute_fake_cycle(
                robot,
                self.hand,
                task_poses_file=str(self.task_poses_file),
                cycle_poses=cycle_poses,
                settle_seconds=self.args.settle_seconds,
                send_order=self.args.send_order,
                mode_resend=self.args.mode_resend,
                step_callback=self._set_step,
                stop_event=self._stop_task_event,
            )
            self.last_issue = None
            self.last_unreachable_target = None
        except WorkflowStopped:
            self.current_mode = "idle"
        except WebConsoleError as exc:
            self.last_issue = {"code": exc.code, "message": exc.message}
            if exc.code == "UNREACHABLE_TARGET":
                self.last_unreachable_target = self._target_signature(best)
            self.current_mode = "error"
        except Exception:
            self.last_issue = {"code": "UNKNOWN_ERROR", "message": "Workflow failed unexpectedly."}
            self.current_mode = "error"
        finally:
            self.busy = False
            self.current_step = None
            if self.camera_ready and self.model_ready:
                self.current_mode = "detecting"
            else:
                self.current_mode = "idle"
            self._stop_task_event.clear()

    def _set_step(self, step: str) -> None:
        self.current_step = step

    def _vision_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                if self.pipeline is None or self.align is None or self.model is None or self.intrinsics is None:
                    time.sleep(0.2)
                    continue
                frames = self.pipeline.wait_for_frames()
                aligned = self.align.process(frames)
                color_frame = aligned.get_color_frame()
                depth_frame = aligned.get_depth_frame()
                if not color_frame or not depth_frame:
                    time.sleep(0.05)
                    continue

                image = np.asanyarray(color_frame.get_data())
                with self._lock:
                    runtime_config = dataclasses.replace(self.runtime_config)

                raw_rows = predict_detection_rows_multirotation(
                    self.model,
                    image,
                    rotate_modes=runtime_config.rotate_inference_modes,
                    device=self.device,
                    conf=self.args.conf,
                    imgsz=runtime_config.imgsz,
                )
                top_detections = [
                    {"class_name": str(row["class_name"]), "confidence": float(row["confidence"])}
                    for row in sorted(raw_rows, key=lambda row: -float(row["confidence"]))[:5]
                ]
                best = choose_target(
                    raw_rows,
                    depth_frame,
                    self.intrinsics,
                    self.base_to_camera,
                    target_labels=runtime_config.target_labels,
                    depth_window=self.args.depth_window,
                )
                detection_state, annotated = self._build_detection_output(image, best, top_detections, runtime_config)
                ok, encoded = cv2.imencode(".jpg", annotated)
                if ok:
                    with self._lock:
                        self.latest_best = best
                        self.latest_detection_state = detection_state
                        self.latest_frame_jpeg = encoded.tobytes()
                if not self.busy:
                    self.current_mode = "detecting"
            except Exception as exc:
                self.camera_ready = False
                self.latest_frame_jpeg = _build_placeholder_frame(f"Vision loop error: {exc}")
                time.sleep(0.2)

    def _build_detection_output(
        self,
        image: np.ndarray,
        best: dict[str, object] | None,
        top_detections: list[dict[str, Any]],
        runtime_config: RuntimeConfig,
    ) -> tuple[dict[str, Any], np.ndarray]:
        frame = image.copy()
        lines = [
            f"mode={self.current_mode}",
            f"targets={','.join(runtime_config.target_labels)}",
            f"imgsz={runtime_config.imgsz} rotate={'+'.join(runtime_config.rotate_inference_modes)}",
        ]
        target_payload = None
        if best is not None:
            x1, y1, x2, y2 = [int(v) for v in best["bbox_xyxy"]]
            cx, cy = [int(v) for v in best["center_xy"]]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
            cv2.circle(frame, (cx, cy), 4, (0, 220, 0), -1)
            label_text = format_target_label(best)
            lines.append(f"target={label_text} conf={float(best['confidence']):.2f}")
            lines.append(f"base=({best['base_xyz_m'][0]:.3f}, {best['base_xyz_m'][1]:.3f}, {best['base_xyz_m'][2]:.3f})")
            target_payload = {
                "class_name": str(best["class_name"]),
                "target_name": str(best.get("target_name", best["class_name"])),
                "confidence": float(best["confidence"]),
                "camera_xyz_m": [float(v) for v in best["camera_xyz_m"]],
                "base_xyz_m": [float(v) for v in best["base_xyz_m"]],
            }
            try:
                cycle_poses = build_cycle_poses(best, runtime_config, str(self.drop_poses_file))
                target_payload["hover_pose"] = [float(v) for v in cycle_poses["target_hover"]]
                target_payload["pregrasp_pose"] = [float(v) for v in cycle_poses["pregrasp_10cm"]]
                target_payload["drop_hover_pose"] = [float(v) for v in cycle_poses["drop_hover"]]
                lines.append(
                    f"hover=({cycle_poses['target_hover'][0]:.3f}, {cycle_poses['target_hover'][1]:.3f}, {cycle_poses['target_hover'][2]:.3f})"
                )
            except WebConsoleError:
                pass
        else:
            lines.append("No valid target")

        for index, line in enumerate(lines):
            cv2.putText(frame, line, (20, 35 + index * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

        return {
            "target": target_payload,
            "top_detections": top_detections,
        }, frame

    def _target_signature(self, best: dict[str, Any] | None) -> dict[str, Any] | None:
        if best is None:
            return None
        base_xyz = best.get("base_xyz_m")
        if not isinstance(base_xyz, (list, tuple)) or len(base_xyz) != 3:
            return None
        return {
            "target_name": str(best.get("target_name", best.get("class_name", ""))),
            "base_xyz_m": [float(v) for v in base_xyz],
        }

    def _same_target(self, best: dict[str, Any] | None, signature: dict[str, Any] | None) -> bool:
        if best is None or signature is None:
            return False
        current_name = str(best.get("target_name", best.get("class_name", "")))
        if current_name != str(signature.get("target_name", "")):
            return False
        base_xyz = best.get("base_xyz_m")
        sign_xyz = signature.get("base_xyz_m")
        if not isinstance(base_xyz, (list, tuple)) or not isinstance(sign_xyz, (list, tuple)) or len(base_xyz) != 3 or len(sign_xyz) != 3:
            return False
        dist_m = float(np.linalg.norm(np.asarray(base_xyz, dtype=np.float64) - np.asarray(sign_xyz, dtype=np.float64)))
        return dist_m <= 0.06

    def mjpeg_generator(self):
        while not self._shutdown_event.is_set():
            with self._lock:
                frame = self.latest_frame_jpeg
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.1)
