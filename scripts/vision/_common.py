from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyrealsense2 as rs
import torch


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_model_path() -> Path:
    return repo_root() / "yolo26s.pt"


def resolve_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if path.is_absolute():
        return path.resolve()
    cwd_path = (Path.cwd() / path).resolve()
    if cwd_path.exists():
        return cwd_path
    return (repo_root() / path).resolve()


def resolve_device(device: str, allow_cpu: bool) -> str:
    if device == "cpu":
        if not allow_cpu:
            raise SystemExit("CPU inference requested but --allow-cpu was not provided")
        return "cpu"
    if torch.cuda.is_available():
        return device
    if allow_cpu:
        print("Warning: CUDA is unavailable; falling back to CPU inference.")
        return "cpu"
    raise SystemExit("CUDA is unavailable. Re-run with --allow-cpu for debug inference.")


def build_pipeline(
    *,
    camera_serial: str,
    width: int,
    height: int,
    fps: int,
    enable_depth: bool,
) -> tuple[rs.pipeline, rs.align | None, rs.pipeline_profile]:
    pipeline = rs.pipeline()
    config = rs.config()
    if camera_serial:
        config.enable_device(camera_serial)
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
    if enable_depth:
        config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
    profile = pipeline.start(config)
    time.sleep(1.0)
    align = rs.align(rs.stream.color) if enable_depth else None
    return pipeline, align, profile


def depth_colormap(depth_frame: rs.depth_frame) -> np.ndarray:
    depth_image = np.asanyarray(depth_frame.get_data())
    depth_scaled = cv2.convertScaleAbs(depth_image, alpha=0.03)
    return cv2.applyColorMap(depth_scaled, cv2.COLORMAP_JET)


def sample_depth_m(depth_frame: rs.depth_frame, u: int, v: int, radius: int) -> float:
    width = depth_frame.get_width()
    height = depth_frame.get_height()
    for dv in range(-radius, radius + 1):
        for du in range(-radius, radius + 1):
            uu = min(max(u + du, 0), width - 1)
            vv = min(max(v + dv, 0), height - 1)
            depth = float(depth_frame.get_distance(uu, vv))
            if depth > 0:
                return depth
    return 0.0


def intrinsics_from_profile(profile: rs.pipeline_profile) -> rs.intrinsics:
    return profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()


def put_lines(image: np.ndarray, lines: list[str], *, x: int = 20, y: int = 30) -> np.ndarray:
    out = image.copy()
    for idx, line in enumerate(lines):
        cv2.putText(
            out,
            line,
            (x, y + idx * 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
    return out


def maybe_insert_script_dir(current_file: str) -> None:
    script_dir = str(Path(current_file).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)


def detection_rows(result: Any) -> list[dict[str, Any]]:
    boxes = result.boxes
    if boxes is None:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confs = boxes.conf.detach().cpu().numpy()
    clses = boxes.cls.detach().cpu().numpy().astype(int)
    rows: list[dict[str, Any]] = []
    for bbox, conf, cls_idx in zip(xyxy, confs, clses):
        x1, y1, x2, y2 = bbox.tolist()
        rows.append(
            {
                "class_id": int(cls_idx),
                "class_name": str(result.names[int(cls_idx)]),
                "confidence": float(conf),
                "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
                "center_xy": [float((x1 + x2) * 0.5), float((y1 + y2) * 0.5)],
            }
        )
    return rows
