#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

from _common import build_pipeline, depth_colormap, put_lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 1: preview RealSense color + depth streams.")
    parser.add_argument("--camera-serial", default="", help="Optional D435 serial number")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline, align, _profile = build_pipeline(
        camera_serial=args.camera_serial,
        width=args.width,
        height=args.height,
        fps=args.fps,
        enable_depth=True,
    )
    assert align is not None

    window_name = "view_realsense_stream"
    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned = align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame or not depth_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())
            depth_image = depth_colormap(depth_frame)
            if depth_image.shape[:2] != color_image.shape[:2]:
                depth_image = cv2.resize(depth_image, (color_image.shape[1], color_image.shape[0]))
            panel = np.hstack([color_image, depth_image])
            panel = put_lines(
                panel,
                [
                    "Left: color stream",
                    "Right: depth colormap",
                    "Press q to quit",
                ],
            )
            cv2.imshow(window_name, panel)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
