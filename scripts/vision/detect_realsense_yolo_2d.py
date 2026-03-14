#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from _common import build_pipeline, default_model_path, detection_rows, put_lines, resolve_device, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 2: run YOLO on the RealSense color stream.")
    parser.add_argument("--model", default=str(default_model_path()), help="Ultralytics model path or name")
    parser.add_argument("--device", default="0", help="Inference device. Use 0 for the first CUDA GPU.")
    parser.add_argument("--allow-cpu", action="store_true", help="Allow CPU inference for debug use")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--camera-serial", default="", help="Optional D435 serial number")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--save-json", default="", help="Optional JSONL file for detections")
    parser.add_argument("--classes", nargs="*", type=int, default=None, help="Optional class id filter")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = resolve_path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model file does not exist: {model_path}")
    device = resolve_device(args.device, args.allow_cpu)
    model = YOLO(str(model_path))
    pipeline, _align, _profile = build_pipeline(
        camera_serial=args.camera_serial,
        width=args.width,
        height=args.height,
        fps=args.fps,
        enable_depth=False,
    )

    output_path = Path(args.save_json).expanduser().resolve() if args.save_json else None
    output_handle = output_path.open("a", encoding="utf-8") if output_path else None
    window_name = "detect_realsense_yolo_2d"
    try:
        while True:
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue
            image = np.asanyarray(color_frame.get_data())
            results = model.predict(
                source=image,
                device=device,
                conf=args.conf,
                classes=args.classes,
                verbose=False,
                stream=False,
            )
            result = results[0]
            annotated = result.plot()
            rows = detection_rows(result)
            for row in rows:
                cx, cy = [int(v) for v in row["center_xy"]]
                cv2.circle(annotated, (cx, cy), 4, (0, 255, 0), -1)
                cv2.putText(
                    annotated,
                    f"({cx}, {cy})",
                    (cx + 6, cy - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                )

            payload = {
                "timestamp_unix": time.time(),
                "image_shape": [int(image.shape[1]), int(image.shape[0])],
                "detections": rows,
            }
            if output_handle is not None:
                output_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                output_handle.flush()

            annotated = put_lines(
                annotated,
                [
                    "Step 2: YOLO 2D detection",
                    f"detections={len(rows)}",
                    "Press q to quit",
                ],
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
