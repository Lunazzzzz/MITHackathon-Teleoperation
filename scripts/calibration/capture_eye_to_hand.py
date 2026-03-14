#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _local_sdk import prefer_local_pyagxarm

prefer_local_pyagxarm(__file__)

from _common import (
    auto_detect_charuco,
    build_charuco_board,
    build_chessboard_object_points,
    detect_chessboard,
    detect_charuco,
    dump_json,
    intrinsics_from_rs,
    load_tcp_offset,
    match_charuco_image_points,
    matrix_to_pose6,
    pose6_to_matrix,
    require_output_dir,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture eye-to-hand samples with a fixed D435 and NERO robot pose.")
    parser.add_argument("--channel", required=True, help="CAN channel name, e.g. can0")
    parser.add_argument("--camera-serial", default="", help="Optional D435 serial number")
    parser.add_argument("--board-type", default="chessboard", choices=["chessboard", "charuco"], help="Calibration target type")
    parser.add_argument("--board-cols", type=int, required=True, help="Chessboard inner-corner width, or ChArUco square count along width")
    parser.add_argument("--board-rows", type=int, required=True, help="Chessboard inner-corner height, or ChArUco square count along height")
    parser.add_argument("--square-size-mm", type=float, required=True, help="Chessboard square size or ChArUco checker size in millimeters")
    parser.add_argument("--marker-size-mm", type=float, default=0.0, help="ChArUco marker size in millimeters")
    parser.add_argument("--aruco-dict", default="auto", help="ChArUco dictionary name, e.g. DICT_4X4_1000, or auto")
    parser.add_argument("--samples", type=int, required=True, help="Number of capture samples to save")
    parser.add_argument("--output-dir", required=True, help="Directory for images and manifest.json")
    parser.add_argument("--tcp-offset-yaml", default="", help="Optional YAML file with a 6-element TCP offset pose")
    parser.add_argument("--width", type=int, default=1280, help="Color stream width")
    parser.add_argument("--height", type=int, default=720, help="Color stream height")
    parser.add_argument("--fps", type=int, default=30, help="Color stream FPS")
    parser.add_argument("--warmup-seconds", type=float, default=1.0, help="Camera warmup time before capture")
    parser.add_argument("--robot", default="nero", help="Robot model passed into pyAgxArm")
    return parser.parse_args()


def wait_for_pose(robot: object, timeout_s: float = 2.0) -> tuple[list[float], list[float] | None]:
    deadline = time.time() + timeout_s
    last_error = None
    while time.time() < deadline:
        try:
            flange_msg = robot.get_flange_pose()
            if flange_msg is None:
                time.sleep(0.05)
                continue
            flange_pose = [float(v) for v in flange_msg.msg]
            tcp_msg = robot.get_tcp_pose()
            tcp_pose = [float(v) for v in tcp_msg.msg] if tcp_msg is not None else None
            return flange_pose, tcp_pose
        except Exception as exc:  # pragma: no cover - hardware path
            last_error = exc
            time.sleep(0.05)
    if last_error is not None:
        raise RuntimeError(f"Failed to read robot pose: {last_error}") from last_error
    raise TimeoutError("Timed out waiting for robot flange pose")


def build_robot(channel: str, robot_name: str, tcp_offset_yaml: str):
    try:
        from pyAgxArm import AgxArmFactory, create_agx_arm_config
    except ImportError as exc:  # pragma: no cover - import error path
        raise SystemExit("pyAgxArm is not installed in the current environment") from exc

    cfg = create_agx_arm_config(robot=robot_name, comm="can", channel=channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    tcp_offset = load_tcp_offset(Path(tcp_offset_yaml)) if tcp_offset_yaml else None
    if tcp_offset is not None:
        robot.set_tcp_offset(tcp_offset)
    return robot, tcp_offset


def build_pipeline(args: argparse.Namespace) -> tuple[rs.pipeline, rs.pipeline_profile]:
    pipeline = rs.pipeline()
    config = rs.config()
    if args.camera_serial:
        config.enable_device(args.camera_serial)
    config.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)
    profile = pipeline.start(config)
    time.sleep(args.warmup_seconds)
    return pipeline, profile


def main() -> int:
    args = parse_args()
    if args.board_type == "charuco" and args.marker_size_mm <= 0.0:
        raise SystemExit("--marker-size-mm must be > 0 when --board-type charuco")
    output_dir = Path(args.output_dir).expanduser().resolve()
    images_dir = output_dir / "images"
    require_output_dir(images_dir)

    robot, tcp_offset = build_robot(args.channel, args.robot, args.tcp_offset_yaml)
    pipeline, profile = build_pipeline(args)
    object_points = (
        build_chessboard_object_points(args.board_cols, args.board_rows, args.square_size_mm)
        if args.board_type == "chessboard"
        else None
    )
    charuco_board = (
        build_charuco_board(args.board_cols, args.board_rows, args.square_size_mm, args.marker_size_mm, args.aruco_dict)
        if args.board_type == "charuco" and args.aruco_dict != "auto"
        else None
    )

    color_intrinsics = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
    manifest: dict[str, object] = {
        "robot": args.robot,
        "channel": args.channel,
        "camera_serial": args.camera_serial,
        "board": {
            "type": args.board_type,
            "cols": args.board_cols,
            "rows": args.board_rows,
            "square_size_mm": args.square_size_mm,
        },
        "camera_intrinsics": intrinsics_from_rs(color_intrinsics),
        "tcp_offset_pose": tcp_offset,
        "created_at_unix": time.time(),
        "samples": [],
    }
    if args.board_type == "charuco":
        manifest["board"]["marker_size_mm"] = args.marker_size_mm
        manifest["board"]["aruco_dict"] = args.aruco_dict

    captured = 0
    window_name = "capture_eye_to_hand"
    print("Controls: press 'c' to capture when the target is stable, 'q' to quit.")

    try:
        while captured < args.samples:
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue
            color_image = np.asanyarray(color_frame.get_data())
            gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)

            display = color_image.copy()
            if args.board_type == "chessboard":
                found, corners = detect_chessboard(gray, args.board_cols, args.board_rows)
                image_points = corners.reshape(-1, 2) if found and corners is not None else None
                sample_object_points = object_points
                charuco_ids = None
                marker_corners = []
                marker_ids = None
                if found and corners is not None:
                    cv2.drawChessboardCorners(display, (args.board_cols, args.board_rows), corners, found)
                detection_count = 0 if image_points is None else int(len(image_points))
                detection_label = f"corners {detection_count}"
            else:
                if charuco_board is None:
                    found, resolved_dict, charuco_board, corners, charuco_ids, marker_corners, marker_ids = auto_detect_charuco(
                        gray,
                        args.board_cols,
                        args.board_rows,
                        args.square_size_mm,
                        args.marker_size_mm,
                    )
                    if resolved_dict is not None and manifest["board"]["aruco_dict"] != resolved_dict:
                        manifest["board"]["aruco_dict"] = resolved_dict
                        print(f"Using ArUco dictionary: {resolved_dict}")
                else:
                    found, corners, charuco_ids, marker_corners, marker_ids = detect_charuco(gray, charuco_board)
                if marker_ids is not None and len(marker_ids) > 0:
                    cv2.aruco.drawDetectedMarkers(display, marker_corners, marker_ids)
                if corners is not None and charuco_ids is not None:
                    cv2.aruco.drawDetectedCornersCharuco(display, corners, charuco_ids)
                    sample_object_points, image_points = match_charuco_image_points(charuco_board, corners, charuco_ids)
                else:
                    sample_object_points, image_points = None, None
                detection_count = 0 if charuco_ids is None else int(len(charuco_ids))
                detection_label = f"charuco {detection_count}"

            cv2.putText(
                display,
                f"captured {captured}/{args.samples}",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0) if found else (0, 0, 255),
                2,
            )
            cv2.putText(
                display,
                detection_label,
                (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0) if found else (0, 0, 255),
                2,
            )
            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key != ord("c"):
                continue
            if not found or image_points is None or sample_object_points is None:
                print("Calibration target not detected; sample skipped.")
                continue

            flange_pose, tcp_pose = wait_for_pose(robot)
            sample_name = f"sample_{captured:03d}"
            image_path = images_dir / f"{sample_name}.png"
            cv2.imwrite(str(image_path), color_image)

            sample = {
                "name": sample_name,
                "image": str(image_path.relative_to(output_dir)),
                "image_size": [int(color_image.shape[1]), int(color_image.shape[0])],
                "captured_at_unix": time.time(),
                "board_corners_px": image_points.astype(float).tolist(),
                "object_points_m": sample_object_points.astype(float).tolist(),
                "flange_pose": flange_pose,
                "flange_transform": pose6_to_matrix(flange_pose).astype(float).tolist(),
                "tcp_pose": tcp_pose,
                "tcp_transform": pose6_to_matrix(tcp_pose).astype(float).tolist() if tcp_pose else None,
            }
            if args.board_type == "charuco" and charuco_ids is not None:
                sample["charuco_ids"] = charuco_ids.reshape(-1).astype(int).tolist()
            manifest["samples"].append(sample)
            captured += 1
            print(f"Saved {sample_name} with flange pose {matrix_to_pose6(pose6_to_matrix(flange_pose))}")
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

    dump_json(output_dir / "manifest.json", manifest)
    print(f"Wrote {len(manifest['samples'])} samples to {output_dir / 'manifest.json'}")
    return 0 if captured == args.samples else 1


if __name__ == "__main__":
    sys.exit(main())
