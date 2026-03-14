#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

from _common import (
    average_transforms,
    build_charuco_board,
    camera_matrix_and_dist_from_manifest,
    detect_charuco,
    dump_json,
    dump_yaml,
    load_yaml,
    match_charuco_image_points,
    matrix_to_dict,
    matrix_to_pose6,
    pose6_to_matrix,
    reprojection_error,
    rt_to_matrix,
    solve_pnp,
    invert_transform,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve fixed-camera eye-to-hand calibration from captured target samples.")
    parser.add_argument("--dataset-dir", required=True, help="Directory containing manifest.json and images/")
    parser.add_argument("--output-yaml", default="", help="Optional explicit output YAML path")
    parser.add_argument(
        "--refine-intrinsics",
        action="store_true",
        help="Recalibrate camera intrinsics from the captured chessboard images instead of using the intrinsics recorded from RealSense.",
    )
    parser.add_argument(
        "--method",
        default="andreff",
        choices=["tsai", "park", "horaud", "andreff", "daniilidis"],
        help="OpenCV hand-eye solver",
    )
    return parser.parse_args()


METHOD_MAP = {
    "tsai": cv2.CALIB_HAND_EYE_TSAI,
    "park": cv2.CALIB_HAND_EYE_PARK,
    "horaud": cv2.CALIB_HAND_EYE_HORAUD,
    "andreff": cv2.CALIB_HAND_EYE_ANDREFF,
    "daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
}


def calibrate_intrinsics(samples: list[dict]) -> tuple[np.ndarray, np.ndarray, list[np.ndarray], list[np.ndarray], float]:
    objpoints = [np.asarray(sample["object_points_m"], dtype=np.float32) for sample in samples]
    imgpoints = [np.asarray(sample["board_corners_px"], dtype=np.float32) for sample in samples]
    height = int(samples[0]["image_size"][1])
    width = int(samples[0]["image_size"][0])
    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        objpoints,
        imgpoints,
        (width, height),
        None,
        None,
    )
    return camera_matrix, dist_coeffs, rvecs, tvecs, float(rms)


def select_robot_pose_key(manifest: dict, samples: list[dict]) -> str:
    tcp_offset = manifest.get("tcp_offset_pose")
    has_tcp_samples = any(sample.get("tcp_pose") is not None for sample in samples)
    if tcp_offset is not None and has_tcp_samples:
        return "tcp_pose"
    return "flange_pose"


def compute_hand_eye(
    samples: list[dict],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    method: int,
    robot_pose_key: str,
) -> tuple[np.ndarray, np.ndarray, list[float], float]:
    rot_gripper_to_base = []
    trans_gripper_to_base = []
    rot_target_to_cam = []
    trans_target_to_cam = []
    per_sample_target = []
    reproj_errors = []

    for sample in samples:
        corners = np.asarray(sample["board_corners_px"], dtype=np.float32)
        object_points = np.asarray(sample["object_points_m"], dtype=np.float32)
        rvec, tvec = solve_pnp(corners, object_points, camera_matrix, dist_coeffs)
        target_to_cam = rt_to_matrix(rvec, tvec)
        base_to_gripper = pose6_to_matrix(sample[robot_pose_key])
        gripper_to_base = invert_transform(base_to_gripper)

        rot_gripper_to_base.append(gripper_to_base[:3, :3])
        trans_gripper_to_base.append(gripper_to_base[:3, 3])
        rot_target_to_cam.append(target_to_cam[:3, :3])
        trans_target_to_cam.append(target_to_cam[:3, 3])
        per_sample_target.append(target_to_cam)
        reproj_errors.append(reprojection_error(object_points, corners, rvec, tvec, camera_matrix, dist_coeffs))

    rot_base_to_camera, trans_base_to_camera = cv2.calibrateHandEye(
        rot_gripper_to_base,
        trans_gripper_to_base,
        rot_target_to_cam,
        trans_target_to_cam,
        method=method,
    )
    base_to_camera = np.eye(4, dtype=np.float64)
    base_to_camera[:3, :3] = rot_base_to_camera
    base_to_camera[:3, 3] = trans_base_to_camera.reshape(3)

    gripper_to_target_candidates = []
    for sample, target_to_cam in zip(samples, per_sample_target):
        base_to_gripper = pose6_to_matrix(sample[robot_pose_key])
        gripper_to_target = invert_transform(base_to_gripper) @ base_to_camera @ target_to_cam
        gripper_to_target_candidates.append(gripper_to_target)

    avg_gripper_to_target = average_transforms(gripper_to_target_candidates)
    return base_to_camera, avg_gripper_to_target, reproj_errors, float(np.mean(reproj_errors))


def add_image_size(samples: list[dict], dataset_dir: Path) -> None:
    for sample in samples:
        if "image_size" in sample and len(sample["image_size"]) == 2:
            continue
        image_path = dataset_dir / sample["image"]
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read image {image_path}")
        sample["image_size"] = [image.shape[1], image.shape[0]]


def populate_charuco_observations(samples: list[dict], dataset_dir: Path, board_cfg: dict) -> None:
    aruco_dict = board_cfg.get("aruco_dict")
    marker_size_mm = float(board_cfg.get("marker_size_mm", 0.0))
    if not aruco_dict or aruco_dict == "auto":
        raise SystemExit("ChArUco datasets must record board.aruco_dict before solving")
    if marker_size_mm <= 0.0:
        raise SystemExit("ChArUco datasets must record board.marker_size_mm before solving")
    board = build_charuco_board(
        int(board_cfg["cols"]),
        int(board_cfg["rows"]),
        float(board_cfg["square_size_mm"]),
        marker_size_mm,
        aruco_dict,
    )
    for sample in samples:
        if sample.get("board_corners_px") and sample.get("object_points_m") and sample.get("charuco_ids"):
            continue
        image_path = dataset_dir / sample["image"]
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read image {image_path}")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, charuco_corners, charuco_ids, _, _ = detect_charuco(gray, board)
        if not found or charuco_corners is None or charuco_ids is None:
            raise RuntimeError(f"Failed to redetect ChArUco corners in {image_path}")
        object_points, image_points = match_charuco_image_points(board, charuco_corners, charuco_ids)
        sample["board_corners_px"] = image_points.astype(float).tolist()
        sample["object_points_m"] = object_points.astype(float).tolist()
        sample["charuco_ids"] = charuco_ids.reshape(-1).astype(int).tolist()


def main() -> int:
    args = parse_args()
    dataset_dir = Path(args.dataset_dir).expanduser().resolve()
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = load_yaml(manifest_path)
    samples = manifest["samples"]
    if len(samples) < 5:
        raise SystemExit("At least 5 samples are required for hand-eye calibration")

    add_image_size(samples, dataset_dir)
    board = manifest["board"]
    if board.get("type") == "charuco":
        populate_charuco_observations(samples, dataset_dir, board)
    robot_pose_key = select_robot_pose_key(manifest, samples)
    camera_matrix, dist_coeffs = camera_matrix_and_dist_from_manifest(manifest)
    rms = float("nan")
    if args.refine_intrinsics:
        camera_matrix, dist_coeffs, _, _, rms = calibrate_intrinsics(samples)
    base_to_camera, gripper_to_target, reproj_errors, mean_error = compute_hand_eye(
        samples,
        camera_matrix,
        dist_coeffs,
        METHOD_MAP[args.method],
        robot_pose_key,
    )

    output_yaml = Path(args.output_yaml).expanduser().resolve() if args.output_yaml else dataset_dir / "calibration_result.yaml"
    output_json = output_yaml.with_suffix(".json")
    result = {
        "solver": {
            "type": "opencv_calibrateHandEye_eye_to_hand",
            "method": args.method,
        },
        "board": board,
        "camera_intrinsics": {
            "camera_matrix": camera_matrix.tolist(),
            "dist_coeffs": dist_coeffs.reshape(-1).tolist(),
            "rms_reprojection_px": rms,
            "source": "calibrateCamera" if args.refine_intrinsics else "manifest",
        },
        "tcp_offset_pose": manifest.get("tcp_offset_pose"),
        "transforms": {
            "T_base_camera": matrix_to_dict(base_to_camera),
            "T_gripper_target": matrix_to_dict(gripper_to_target),
        },
        "metrics": {
            "mean_pnp_reprojection_px": mean_error,
            "per_sample_pnp_reprojection_px": reproj_errors,
            "sample_count": len(samples),
        },
        "notes": {
            "frame_convention": "T_a_b maps points from frame b into frame a",
            "robot_pose_source": f"pyAgxArm get_{robot_pose_key}()",
            "robot_pose_frame": "tcp" if robot_pose_key == "tcp_pose" else "flange",
        },
    }
    dump_yaml(output_yaml, result)
    dump_json(output_json, result)

    print(f"Saved calibration result to {output_yaml}")
    print(f"Saved calibration result to {output_json}")
    if args.refine_intrinsics:
        print(f"Camera RMS reprojection error: {rms:.4f} px")
    else:
        print("Camera RMS reprojection error: n/a (using intrinsics from manifest)")
    print(f"Mean solvePnP reprojection error: {mean_error:.4f} px")
    print(f"T_base_camera pose6: {matrix_to_pose6(base_to_camera)}")
    print(f"T_gripper_target pose6: {matrix_to_pose6(gripper_to_target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
