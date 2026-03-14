#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs
import torch
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO11 on a live RealSense color stream using GPU.")
    parser.add_argument("--model", default="yolo11s.pt", help="Ultralytics model path or name")
    parser.add_argument("--device", default="0", help="Inference device. Use 0 for the first CUDA GPU.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--camera-serial", default="", help="Optional D435 serial number")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--save-json", default="", help="Optional JSONL file for detections")
    parser.add_argument("--classes", nargs="*", type=int, default=None, help="Optional class filter")
    return parser.parse_args()


def require_cuda(device: str) -> None:
    if str(device) in {"cpu", "mps"}:
        raise SystemExit("GPU is required for this script; do not use CPU or MPS")
    if not torch.cuda.is_available():
        raise SystemExit("torch.cuda.is_available() is False; GPU setup is incomplete")


def build_pipeline(args: argparse.Namespace) -> rs.pipeline:
    pipeline = rs.pipeline()
    config = rs.config()
    if args.camera_serial:
        config.enable_device(args.camera_serial)
    config.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)
    pipeline.start(config)
    time.sleep(1.0)
    return pipeline


def main() -> int:
    args = parse_args()
    require_cuda(args.device)
    model = YOLO(args.model)
    pipeline = build_pipeline(args)
    output_path = Path(args.save_json).expanduser().resolve() if args.save_json else None
    output_handle = output_path.open("a", encoding="utf-8") if output_path else None

    window_name = "yolo_detect_realsense"
    try:
        while True:
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue
            image = np.asanyarray(color_frame.get_data())
            results = model.predict(
                source=image,
                device=args.device,
                conf=args.conf,
                classes=args.classes,
                verbose=False,
                stream=False,
            )
            result = results[0]
            annotated = result.plot()
            payload = {
                "timestamp_unix": time.time(),
                "image_shape": [int(image.shape[1]), int(image.shape[0])],
                "detections": [],
            }

            names = result.names
            boxes = result.boxes
            if boxes is not None:
                xyxy = boxes.xyxy.detach().cpu().numpy()
                confs = boxes.conf.detach().cpu().numpy()
                clses = boxes.cls.detach().cpu().numpy().astype(int)
                for bbox, conf, cls_idx in zip(xyxy, confs, clses):
                    x1, y1, x2, y2 = bbox.tolist()
                    payload["detections"].append(
                        {
                            "class_id": int(cls_idx),
                            "class_name": names[int(cls_idx)],
                            "confidence": float(conf),
                            "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
                            "center_xy": [float((x1 + x2) * 0.5), float((y1 + y2) * 0.5)],
                        }
                    )
            if output_handle is not None:
                output_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                output_handle.flush()

            cv2.imshow(window_name, annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        if output_handle is not None:
            output_handle.close()
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
