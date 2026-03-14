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
    load_yaml,
    match_charuco_image_points,
    matrix_to_pose6,
    pose6_to_matrix,
    reprojection_error,
    rt_to_matrix,
    solve_pnp,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a fixed-camera eye-to-hand result with live calibration target observations.")
    parser.add_argument("--calibration-file", required=True, help="Path to calibration_result.yaml")
    parser.add_argument("--channel", required=True, help="CAN channel name, e.g. can0")
    parser.add_argument("--camera-serial", default="", help="Optional D435 serial number")
    parser.add_argument("--samples", type=int, default=5, help="Verification samples to capture")
    parser.add_argument("--output-json", default="", help="Optional explicit verification report path")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--robot", default="nero")
    return parser.parse_args()


def build_robot(channel: str, robot_name: str, tcp_offset: list[float] | None):
    from pyAgxArm import AgxArmFactory, create_agx_arm_config

    cfg = create_agx_arm_config(robot=robot_name, comm="can", channel=channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    if tcp_offset is not None:
        robot.set_tcp_offset(tcp_offset)
    return robot


def wait_for_robot_pose(robot: object, pose_frame: str, timeout_s: float = 2.0) -> list[float]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pose_msg = robot.get_tcp_pose() if pose_frame == "tcp" else robot.get_flange_pose()
        if pose_msg is not None:
            return [float(v) for v in pose_msg.msg]
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for {pose_frame} pose")


def build_pipeline(args: argparse.Namespace) -> rs.pipeline:
    pipeline = rs.pipeline()
    config = rs.config()
    if args.camera_serial:
        config.enable_device(args.camera_serial)
    config.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)
    pipeline.start(config)
    time.sleep(1.0)
    return pipeline


def rotation_error_deg(rot_a: np.ndarray, rot_b: np.ndarray) -> float:
    delta = rot_a.T @ rot_b
    trace = np.clip((np.trace(delta) - 1.0) * 0.5, -1.0, 1.0)
    return float(np.degrees(np.arccos(trace)))


def main() -> int:
    args = parse_args()
    calibration_path = Path(args.calibration_file).expanduser().resolve()
    calibration = load_yaml(calibration_path)
    board = calibration["board"]
    board_type = board.get("type", "chessboard")
    object_points = (
        build_chessboard_object_points(board["cols"], board["rows"], board["square_size_mm"])
        if board_type == "chessboard"
        else None
    )
    charuco_board = None
    if board_type == "charuco":
        aruco_dict = board.get("aruco_dict")
        marker_size_mm = float(board.get("marker_size_mm", 0.0))
        if aruco_dict and aruco_dict != "auto" and marker_size_mm > 0.0:
            charuco_board = build_charuco_board(
                int(board["cols"]),
                int(board["rows"]),
                float(board["square_size_mm"]),
                marker_size_mm,
                aruco_dict,
            )

    intrinsics_block = calibration["camera_intrinsics"]
    camera_matrix = np.asarray(intrinsics_block["camera_matrix"], dtype=np.float64)
    dist_coeffs = np.asarray(intrinsics_block["dist_coeffs"], dtype=np.float64)
    base_to_camera = np.asarray(calibration["transforms"]["T_base_camera"]["matrix"], dtype=np.float64)
    gripper_to_target = np.asarray(calibration["transforms"]["T_gripper_target"]["matrix"], dtype=np.float64)
    notes = calibration.get("notes", {})
    pose_frame = notes.get("robot_pose_frame", "flange")
    tcp_offset = calibration.get("tcp_offset_pose") if pose_frame == "tcp" else None

    robot = build_robot(args.channel, args.robot, tcp_offset)
    pipeline = build_pipeline(args)
    report = {"samples": []}
    window_name = "verify_eye_to_hand"

    print("Controls: press 'c' to capture a verification sample, 'q' to quit.")
    try:
        while len(report["samples"]) < args.samples:
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue
            color_image = np.asanyarray(color_frame.get_data())
            gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)

            display = color_image.copy()
            if board_type == "chessboard":
                found, corners = detect_chessboard(gray, board["cols"], board["rows"])
                image_points = corners.reshape(-1, 2) if found and corners is not None else None
                sample_object_points = object_points
                if found and corners is not None:
                    cv2.drawChessboardCorners(display, (board["cols"], board["rows"]), corners, found)
                detection_label = f"corners {0 if image_points is None else len(image_points)}"
            else:
                if charuco_board is None:
                    found, resolved_dict, charuco_board, corners, charuco_ids, marker_corners, marker_ids = auto_detect_charuco(
                        gray,
                        int(board["cols"]),
                        int(board["rows"]),
                        float(board["square_size_mm"]),
                        float(board["marker_size_mm"]),
                    )
                    if resolved_dict and board.get("aruco_dict") != resolved_dict:
                        board["aruco_dict"] = resolved_dict
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
                detection_label = f"charuco {0 if corners is None else len(corners)}"
            cv2.putText(
                display,
                f"verify {len(report['samples'])}/{args.samples}",
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

            robot_pose = wait_for_robot_pose(robot, pose_frame)
            rvec, tvec = solve_pnp(image_points, sample_object_points, camera_matrix, dist_coeffs)
            camera_to_target = rt_to_matrix(rvec, tvec)
            predicted_target_in_base = pose6_to_matrix(robot_pose) @ gripper_to_target
            observed_target_in_base = base_to_camera @ camera_to_target

            translation_error_m = float(
                np.linalg.norm(predicted_target_in_base[:3, 3] - observed_target_in_base[:3, 3])
            )
            rotation_error = rotation_error_deg(
                predicted_target_in_base[:3, :3], observed_target_in_base[:3, :3]
            )
            pnp_error = reprojection_error(sample_object_points, image_points, rvec, tvec, camera_matrix, dist_coeffs)
            report["samples"].append(
                {
                    "robot_pose_frame": pose_frame,
                    "robot_pose": robot_pose,
                    "predicted_target_pose": matrix_to_pose6(predicted_target_in_base),
                    "observed_target_pose": matrix_to_pose6(observed_target_in_base),
                    "translation_error_mm": translation_error_m * 1000.0,
                    "rotation_error_deg": rotation_error,
                    "pnp_reprojection_px": pnp_error,
                }
            )
            print(
                f"sample {len(report['samples'])}: "
                f"translation={translation_error_m * 1000.0:.2f} mm, "
                f"rotation={rotation_error:.2f} deg, pnp={pnp_error:.3f} px"
            )
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()

    if not report["samples"]:
        return 1

    report["summary"] = {
        "mean_translation_error_mm": float(np.mean([s["translation_error_mm"] for s in report["samples"]])),
        "max_translation_error_mm": float(np.max([s["translation_error_mm"] for s in report["samples"]])),
        "mean_rotation_error_deg": float(np.mean([s["rotation_error_deg"] for s in report["samples"]])),
        "mean_pnp_reprojection_px": float(np.mean([s["pnp_reprojection_px"] for s in report["samples"]])),
    }
    output_path = (
        Path(args.output_json).expanduser().resolve()
        if args.output_json
        else calibration_path.with_name("verification_report.json")
    )
    dump_json(output_path, report)
    print(f"Verification report saved to {output_path}")
    print(report["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
