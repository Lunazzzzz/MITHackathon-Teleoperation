from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyrealsense2 as rs
import torch

VALID_ROTATE_INFERENCE_MODES = ("none", "cw90", "ccw90", "180")


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
    color_auto_exposure: bool | None = None,
    color_exposure: float | None = None,
    color_gain: float | None = None,
    color_auto_white_balance: bool | None = None,
    color_white_balance: float | None = None,
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
    configure_color_sensor(
        profile,
        auto_exposure=color_auto_exposure,
        exposure=color_exposure,
        gain=color_gain,
        auto_white_balance=color_auto_white_balance,
        white_balance=color_white_balance,
    )
    time.sleep(0.2)
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


def rotate_image_for_inference(image: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return image
    if mode == "cw90":
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if mode == "ccw90":
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if mode == "180":
        return cv2.rotate(image, cv2.ROTATE_180)
    raise ValueError(f"Unsupported rotate mode: {mode}")


def inverse_rotate_point(x: float, y: float, width: int, height: int, mode: str) -> tuple[float, float]:
    if mode == "none":
        return float(x), float(y)
    if mode == "cw90":
        return float(y), float(height - 1 - x)
    if mode == "ccw90":
        return float(width - 1 - y), float(x)
    if mode == "180":
        return float(width - 1 - x), float(height - 1 - y)
    raise ValueError(f"Unsupported rotate mode: {mode}")


def inverse_rotate_bbox(bbox_xyxy: list[float], width: int, height: int, mode: str) -> list[float]:
    x1, y1, x2, y2 = [float(v) for v in bbox_xyxy]
    corners = [
        inverse_rotate_point(x1, y1, width, height, mode),
        inverse_rotate_point(x2, y1, width, height, mode),
        inverse_rotate_point(x1, y2, width, height, mode),
        inverse_rotate_point(x2, y2, width, height, mode),
    ]
    xs = [pt[0] for pt in corners]
    ys = [pt[1] for pt in corners]
    return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]


def map_detection_rows_to_original(
    rows: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    rotate_mode: str,
) -> list[dict[str, Any]]:
    if rotate_mode == "none":
        return rows
    mapped_rows: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        if "bbox_xyxy" in mapped:
            mapped["bbox_xyxy"] = inverse_rotate_bbox(mapped["bbox_xyxy"], image_width, image_height, rotate_mode)
        if "center_xy" in mapped:
            cx, cy = [float(v) for v in mapped["center_xy"]]
            mapped["center_xy"] = list(inverse_rotate_point(cx, cy, image_width, image_height, rotate_mode))
        mapped["inference_rotate_mode"] = rotate_mode
        mapped_rows.append(mapped)
    return mapped_rows


def normalize_rotate_inference_modes(single_mode: str, multi_modes: list[str] | None = None) -> list[str]:
    requested = multi_modes if multi_modes else [single_mode]
    normalized: list[str] = []
    for mode in requested:
        if mode not in VALID_ROTATE_INFERENCE_MODES:
            raise ValueError(f"Unsupported rotate mode: {mode}")
        if mode not in normalized:
            normalized.append(mode)
    return normalized or ["none"]


def bbox_iou(box_a: list[float], box_b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = [float(v) for v in box_a]
    bx1, by1, bx2, by2 = [float(v) for v in box_b]
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0.0:
        return 0.0
    return float(inter_area / union)


def merge_detection_rows(
    rows: list[dict[str, Any]],
    *,
    max_center_distance_px: float = 40.0,
    min_iou: float = 0.25,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: float(item.get("confidence", 0.0)), reverse=True):
        row_mode = str(row.get("inference_rotate_mode", "none"))
        matched = None
        for existing in merged:
            if str(existing.get("class_name")) != str(row.get("class_name")):
                continue
            same_center = center_distance_px(existing, row) <= max_center_distance_px
            same_box = bbox_iou(existing["bbox_xyxy"], row["bbox_xyxy"]) >= min_iou
            if same_center or same_box:
                matched = existing
                break
        if matched is None:
            cloned = clone_detection_row(row)
            assert cloned is not None
            cloned["inference_rotate_modes"] = [row_mode]
            merged.append(cloned)
            continue
        rotate_modes = list(matched.get("inference_rotate_modes", []))
        if row_mode not in rotate_modes:
            rotate_modes.append(row_mode)
        matched["inference_rotate_modes"] = rotate_modes
        if float(row.get("confidence", 0.0)) > float(matched.get("confidence", 0.0)):
            best = clone_detection_row(row)
            assert best is not None
            for key, value in best.items():
                matched[key] = value
            matched["inference_rotate_modes"] = rotate_modes
    return merged


def predict_detection_rows_multirotation(
    model: Any,
    image: np.ndarray,
    *,
    rotate_modes: list[str],
    device: str,
    conf: float,
    imgsz: int,
    classes: list[int] | None = None,
) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    for mode in rotate_modes:
        infer_image = rotate_image_for_inference(image, mode)
        predict_kwargs: dict[str, Any] = {
            "source": infer_image,
            "device": device,
            "conf": conf,
            "imgsz": imgsz,
            "verbose": False,
            "stream": False,
        }
        if classes is not None:
            predict_kwargs["classes"] = classes
        result = model.predict(**predict_kwargs)[0]
        all_rows.extend(
            map_detection_rows_to_original(
                detection_rows(result),
                image_width=image.shape[1],
                image_height=image.shape[0],
                rotate_mode=mode,
            )
        )
    return merge_detection_rows(all_rows)


def clone_detection_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    cloned = dict(row)
    for key in ("bbox_xyxy", "center_xy", "camera_xyz_m", "base_xyz_m"):
        if cloned.get(key) is not None:
            cloned[key] = [float(v) for v in cloned[key]]
    if cloned.get("depth_m") is not None:
        cloned["depth_m"] = float(cloned["depth_m"])
    if cloned.get("confidence") is not None:
        cloned["confidence"] = float(cloned["confidence"])
    return cloned


def detection_label(row: dict[str, Any]) -> str:
    target_name = row.get("target_name")
    if target_name:
        return str(target_name)
    return str(row.get("class_name", ""))


def center_distance_px(row_a: dict[str, Any], row_b: dict[str, Any]) -> float:
    center_a = np.asarray(row_a["center_xy"], dtype=np.float64)
    center_b = np.asarray(row_b["center_xy"], dtype=np.float64)
    return float(np.linalg.norm(center_a - center_b))


def average_detection_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("rows must not be empty")
    averaged = clone_detection_row(rows[-1])
    assert averaged is not None
    for key in ("bbox_xyxy", "center_xy", "camera_xyz_m", "base_xyz_m"):
        values = [np.asarray(row[key], dtype=np.float64) for row in rows if row.get(key) is not None]
        if values:
            averaged[key] = np.mean(values, axis=0).tolist()
    confidences = [float(row["confidence"]) for row in rows if row.get("confidence") is not None]
    if confidences:
        averaged["confidence"] = float(np.mean(confidences))
    depths = [float(row["depth_m"]) for row in rows if row.get("depth_m") is not None]
    if depths:
        averaged["depth_m"] = float(np.mean(depths))
    averaged["stable_hits"] = len(rows)
    return averaged


class DetectionStabilizer:
    def __init__(
        self,
        *,
        window_frames: int,
        min_hits: int,
        max_center_distance_px: float,
        hold_seconds: float,
    ) -> None:
        self.window_frames = max(1, int(window_frames))
        self.min_hits = max(1, int(min_hits))
        self.max_center_distance_px = max(0.0, float(max_center_distance_px))
        self.hold_seconds = max(0.0, float(hold_seconds))
        self.history: deque[dict[str, Any] | None] = deque(maxlen=self.window_frames)
        self.last_stable: dict[str, Any] | None = None
        self.last_stable_ts = 0.0

    def _matching_rows(self, anchor: dict[str, Any]) -> list[dict[str, Any]]:
        label = detection_label(anchor)
        matches: list[dict[str, Any]] = []
        for row in self.history:
            if row is None:
                continue
            if detection_label(row) != label:
                continue
            if center_distance_px(row, anchor) > self.max_center_distance_px:
                continue
            matches.append(row)
        return matches

    def update(self, rows: list[dict[str, Any]], *, now: float | None = None) -> dict[str, Any] | None:
        timestamp = time.time() if now is None else float(now)
        current = clone_detection_row(rows[0]) if rows else None
        self.history.append(current)

        if current is not None:
            matches = self._matching_rows(current)
            if len(matches) >= self.min_hits:
                stable = average_detection_rows(matches)
                stable["unstable"] = False
                stable["stale"] = False
                stable["stable_hits"] = len(matches)
                self.last_stable = clone_detection_row(stable)
                self.last_stable_ts = timestamp
                return stable
            current["unstable"] = True
            current["stale"] = False
            current["stable_hits"] = len(matches)
            return current

        if self.last_stable is not None and timestamp - self.last_stable_ts <= self.hold_seconds:
            stale = clone_detection_row(self.last_stable)
            assert stale is not None
            stale["unstable"] = False
            stale["stale"] = True
            return stale
        return None


def _get_color_sensor(profile: rs.pipeline_profile) -> rs.sensor | None:
    device = profile.get_device()
    for sensor in device.query_sensors():
        try:
            name = sensor.get_info(rs.camera_info.name)
        except Exception:
            name = ""
        if "RGB" in name or "Color" in name:
            return sensor
    sensors = device.query_sensors()
    return sensors[0] if sensors else None


def _set_sensor_option(sensor: rs.sensor | None, option: rs.option, value: float, label: str) -> None:
    if sensor is None:
        return
    try:
        if not sensor.supports(option):
            print(f"Warning: RealSense color sensor does not support {label}.")
            return
        sensor.set_option(option, float(value))
    except Exception as exc:
        print(f"Warning: failed to set RealSense {label}={value}: {exc}")


def configure_color_sensor(
    profile: rs.pipeline_profile,
    *,
    auto_exposure: bool | None,
    exposure: float | None,
    gain: float | None,
    auto_white_balance: bool | None,
    white_balance: float | None,
) -> None:
    if all(value is None for value in (auto_exposure, exposure, gain, auto_white_balance, white_balance)):
        return
    sensor = _get_color_sensor(profile)
    if sensor is None:
        print("Warning: could not find a RealSense color sensor to configure.")
        return
    if auto_exposure is not None:
        _set_sensor_option(sensor, rs.option.enable_auto_exposure, 1.0 if auto_exposure else 0.0, "auto_exposure")
    if auto_exposure is False:
        if exposure is not None:
            _set_sensor_option(sensor, rs.option.exposure, exposure, "exposure")
        if gain is not None:
            _set_sensor_option(sensor, rs.option.gain, gain, "gain")
    if auto_white_balance is not None:
        _set_sensor_option(
            sensor,
            rs.option.enable_auto_white_balance,
            1.0 if auto_white_balance else 0.0,
            "auto_white_balance",
        )
    if auto_white_balance is False and white_balance is not None:
        _set_sensor_option(sensor, rs.option.white_balance, white_balance, "white_balance")
