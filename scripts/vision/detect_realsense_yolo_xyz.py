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

from _common import (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Step 3: run YOLO on RealSense and print candidate grasp points in camera XYZ and optional base XYZ."
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
    parser.add_argument(
        "--target-labels",
        nargs="*",
        default=["cup", "bottle"],
        help="Class names to keep. Defaults to cup bottle.",
    )
    parser.add_argument(
        "--keep-last-seconds",
        type=float,
        default=0.8,
        help="Keep showing the last valid cup/bottle result for this many seconds when detection flickers.",
    )
    parser.add_argument(
        "--calibration-file",
        default="",
        help="Optional calibration_result.yaml used to transform camera XYZ into robot base XYZ.",
    )
    parser.add_argument("--save-json", default="", help="Optional JSONL file for XYZ detections")
    return parser.parse_args()


def load_base_to_camera(path_str: str) -> tuple[Path, np.ndarray]:
    path = resolve_path(path_str)
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


def draw_target_box(
    image: np.ndarray,
    row: dict[str, object],
    *,
    primary: bool,
) -> None:
    x1, y1, x2, y2 = [int(v) for v in row["bbox_xyxy"]]
    cx, cy = [int(v) for v in row["center_xy"]]
    stale = bool(row.get("stale"))
    fallback = bool(row.get("fallback"))
    if stale:
        color = (120, 200, 200)
    elif fallback:
        color = (0, 160, 255)
    else:
        color = (0, 220, 0) if primary else (0, 160, 255)
    thickness = 3 if primary else 2
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    cv2.circle(image, (cx, cy), 5, color, -1)
    cv2.drawMarker(image, (cx, cy), color, cv2.MARKER_CROSS, 18, 2)

    title = f"{row['class_name']} conf={float(row['confidence']):.2f}"
    if stale:
        title += " stale"
    elif fallback:
        title += " fallback"
    if row.get("camera_xyz_m") is None:
        detail = "depth=NA cam=NA"
    else:
        xyz = row["camera_xyz_m"]
        detail = (
            f"depth={float(row['depth_m']):.3f}m "
            f"cam=({float(xyz[0]):.3f}, {float(xyz[1]):.3f}, {float(xyz[2]):.3f})"
        )
        if row.get("base_xyz_m") is not None:
            base = row["base_xyz_m"]
            detail += f" base=({float(base[0]):.3f}, {float(base[1]):.3f}, {float(base[2]):.3f})"
    cv2.putText(image, title, (x1, max(24, y1 - 24)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.putText(image, detail, (x1, max(48, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def build_overlay_lines(rows: list[dict[str, object]], calibration_path: Path | None) -> list[str]:
    if not rows:
        lines = [
            "Step 3: YOLO + depth -> camera XYZ",
            "targets=cup,bottle",
            "No cup/bottle detected",
        ]
        if calibration_path is not None:
            lines.append(f"base frame={calibration_path.name}")
        lines.append("Press q to quit")
        return lines

    best = rows[0]
    center_xy = [int(v) for v in best["center_xy"]]
    status = "primary"
    if bool(best.get("stale")):
        status = "last-known"
    elif bool(best.get("fallback")):
        status = "fallback"
    lines = [
        "Step 3: YOLO + depth -> camera XYZ",
        f"targets={','.join(sorted({str(row['class_name']) for row in rows}))}",
        f"{status}={best['class_name']} conf={float(best['confidence']):.2f} pixel={center_xy}",
    ]
    if best.get("camera_xyz_m") is None:
        lines.append("depth=NA cam=NA")
    else:
        xyz = best["camera_xyz_m"]
        lines.append(
            f"depth={float(best['depth_m']):.3f}m "
            f"X={float(xyz[0]):.3f} Y={float(xyz[1]):.3f} Z={float(xyz[2]):.3f}"
        )
        if best.get("base_xyz_m") is not None:
            base = best["base_xyz_m"]
            lines.append(
                f"base X={float(base[0]):.3f} Y={float(base[1]):.3f} Z={float(base[2]):.3f}"
            )
    if calibration_path is not None:
        lines.append(f"calibration={calibration_path.name}")
    lines.append("Press q to quit")
    return lines


def clone_row(row: dict[str, object]) -> dict[str, object]:
    cloned = dict(row)
    if "bbox_xyxy" in cloned:
        cloned["bbox_xyxy"] = [float(v) for v in cloned["bbox_xyxy"]]
    if "center_xy" in cloned:
        cloned["center_xy"] = [float(v) for v in cloned["center_xy"]]
    if cloned.get("camera_xyz_m") is not None:
        cloned["camera_xyz_m"] = [float(v) for v in cloned["camera_xyz_m"]]
    if cloned.get("base_xyz_m") is not None:
        cloned["base_xyz_m"] = [float(v) for v in cloned["base_xyz_m"]]
    return cloned


def main() -> int:
    args = parse_args()
    model_path = resolve_path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model file does not exist: {model_path}")
    device = resolve_device(args.device, args.allow_cpu)
    model = YOLO(str(model_path))
    calibration_path = None
    base_to_camera = None
    if args.calibration_file:
        calibration_path, base_to_camera = load_base_to_camera(args.calibration_file)
    pipeline, align, profile = build_pipeline(
        camera_serial=args.camera_serial,
        width=args.width,
        height=args.height,
        fps=args.fps,
        enable_depth=True,
    )
    assert align is not None
    intrinsics = intrinsics_from_profile(profile)

    output_path = Path(args.save_json).expanduser().resolve() if args.save_json else None
    output_handle = output_path.open("a", encoding="utf-8") if output_path else None
    target_labels = set(args.target_labels)
    window_name = "detect_realsense_yolo_xyz"
    last_print_s = 0.0
    last_primary: dict[str, object] | None = None
    last_primary_ts = 0.0

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
            all_rows = []
            target_rows = []
            for row in detection_rows(result):
                if target_labels and row["class_name"] not in target_labels:
                    all_rows.append(row)
                    continue
                cx, cy = [int(v) for v in row["center_xy"]]
                depth_m = sample_depth_m(depth_frame, cx, cy, args.depth_window)
                point_xyz = None
                point_base = None
                if depth_m > 0:
                    point_xyz = rs.rs2_deproject_pixel_to_point(intrinsics, [cx, cy], depth_m)
                    if base_to_camera is not None:
                        point_camera = np.asarray(point_xyz, dtype=np.float64)
                        point_base = (base_to_camera[:3, :3] @ point_camera) + base_to_camera[:3, 3]
                row["depth_m"] = float(depth_m)
                row["camera_xyz_m"] = [float(v) for v in point_xyz] if point_xyz is not None else None
                row["base_xyz_m"] = [float(v) for v in point_base] if point_base is not None else None
                target_rows.append(row)
            target_rows.sort(key=lambda row: float(row["confidence"]), reverse=True)
            all_rows.sort(key=lambda row: float(row["confidence"]), reverse=True)

            rows = target_rows
            now = time.time()
            if target_rows:
                last_primary = clone_row(target_rows[0])
                last_primary["stale"] = False
                last_primary["fallback"] = False
                last_primary_ts = now
            elif last_primary is not None and now - last_primary_ts <= max(0.0, args.keep_last_seconds):
                stale_row = clone_row(last_primary)
                stale_row["stale"] = True
                rows = [stale_row]
            elif all_rows:
                fallback = clone_row(all_rows[0])
                fallback["depth_m"] = math.nan
                fallback["camera_xyz_m"] = None
                fallback["fallback"] = True
                rows = [fallback]

            annotated = image.copy()
            for idx, row in enumerate(rows):
                draw_target_box(annotated, row, primary=(idx == 0))

            payload = {
                "timestamp_unix": time.time(),
                "image_shape": [int(image.shape[1]), int(image.shape[0])],
                "detections": rows,
            }
            if output_handle is not None:
                output_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                output_handle.flush()

            if rows and now - last_print_s >= 1.0:
                best = rows[0]
                print(
                    f"{best['class_name']} conf={best['confidence']:.3f} "
                    f"pixel={best['center_xy']} depth={best['depth_m']:.3f} "
                    f"camera_xyz={best['camera_xyz_m']} "
                    f"base_xyz={best.get('base_xyz_m')}"
                )
                last_print_s = now

            annotated = put_lines(
                annotated,
                build_overlay_lines(rows, calibration_path),
            )
            cv2.imshow(window_name, annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        if output_handle is not None:
            output_handle.close()
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
