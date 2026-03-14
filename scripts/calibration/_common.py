from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from scipy.spatial.transform import Rotation

ARUCO_DICT_NAMES = [
    "DICT_4X4_50",
    "DICT_4X4_100",
    "DICT_4X4_250",
    "DICT_4X4_1000",
    "DICT_5X5_50",
    "DICT_5X5_100",
    "DICT_5X5_250",
    "DICT_5X5_1000",
    "DICT_6X6_50",
    "DICT_6X6_100",
    "DICT_6X6_250",
    "DICT_6X6_1000",
    "DICT_7X7_50",
    "DICT_7X7_100",
    "DICT_7X7_250",
    "DICT_7X7_1000",
]


def rpy_to_rot(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=np.float64,
    )


def rot_to_rpy(rot: np.ndarray) -> list[float]:
    r20 = float(rot[2, 0])
    pitch = math.asin(max(-1.0, min(1.0, -r20)))
    cp = math.cos(pitch)
    eps = 1e-9
    if abs(cp) < eps:
        roll = 0.0
        yaw = math.atan2(-rot[0, 1], rot[1, 1])
    else:
        roll = math.atan2(rot[2, 1], rot[2, 2])
        yaw = math.atan2(rot[1, 0], rot[0, 0])
    return [roll, pitch, yaw]


def pose6_to_matrix(pose: list[float]) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = rpy_to_rot(pose[3], pose[4], pose[5])
    mat[:3, 3] = np.asarray(pose[:3], dtype=np.float64)
    return mat


def matrix_to_pose6(mat: np.ndarray) -> list[float]:
    return [
        float(mat[0, 3]),
        float(mat[1, 3]),
        float(mat[2, 3]),
        *[float(v) for v in rot_to_rpy(mat[:3, :3])],
    ]


def invert_transform(mat: np.ndarray) -> np.ndarray:
    inv = np.eye(4, dtype=np.float64)
    rot = mat[:3, :3]
    trans = mat[:3, 3]
    inv[:3, :3] = rot.T
    inv[:3, 3] = -rot.T @ trans
    return inv


def average_transforms(transforms: list[np.ndarray]) -> np.ndarray:
    if not transforms:
        raise ValueError("No transforms to average")
    rot = Rotation.from_matrix([mat[:3, :3] for mat in transforms]).mean().as_matrix()
    trans = np.mean([mat[:3, 3] for mat in transforms], axis=0)
    avg = np.eye(4, dtype=np.float64)
    avg[:3, :3] = rot
    avg[:3, 3] = trans
    return avg


def matrix_to_dict(mat: np.ndarray) -> dict[str, Any]:
    return {
        "matrix": [[float(v) for v in row] for row in mat],
        "pose6": matrix_to_pose6(mat),
        "translation_m": [float(v) for v in mat[:3, 3]],
        "rotation_rpy_rad": [float(v) for v in rot_to_rpy(mat[:3, :3])],
    }


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def dump_yaml(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def dump_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def build_chessboard_object_points(board_cols: int, board_rows: int, square_size_mm: float) -> np.ndarray:
    obj = np.zeros((board_rows * board_cols, 3), dtype=np.float32)
    obj[:, :2] = np.mgrid[0:board_cols, 0:board_rows].T.reshape(-1, 2)
    obj *= square_size_mm / 1000.0
    return obj


def get_aruco_dictionary(dict_name: str):
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("OpenCV ArUco module is not available in this environment")
    if not dict_name or not hasattr(cv2.aruco, dict_name):
        raise ValueError(f"Unsupported ArUco dictionary: {dict_name}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))


def build_charuco_board(
    board_cols: int,
    board_rows: int,
    square_size_mm: float,
    marker_size_mm: float,
    aruco_dict_name: str,
):
    return cv2.aruco.CharucoBoard(
        (board_cols, board_rows),
        square_size_mm / 1000.0,
        marker_size_mm / 1000.0,
        get_aruco_dictionary(aruco_dict_name),
    )


def detect_chessboard(gray: np.ndarray, board_cols: int, board_rows: int) -> tuple[bool, np.ndarray | None]:
    pattern = (board_cols, board_rows)
    found, corners = cv2.findChessboardCornersSB(gray, pattern, flags=cv2.CALIB_CB_EXHAUSTIVE)
    if not found:
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
        found, corners = cv2.findChessboardCorners(gray, pattern, flags=flags)
        if found:
            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001,
            )
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return found, corners


def detect_charuco(gray: np.ndarray, board) -> tuple[bool, np.ndarray | None, np.ndarray | None, list[np.ndarray], np.ndarray | None]:
    marker_corners, marker_ids, _ = cv2.aruco.detectMarkers(gray, board.getDictionary())
    if marker_ids is None or len(marker_ids) == 0:
        return False, None, None, marker_corners, marker_ids
    found_count, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
        marker_corners,
        marker_ids,
        gray,
        board,
    )
    found = charuco_corners is not None and charuco_ids is not None and int(found_count) >= 6
    return found, charuco_corners, charuco_ids, marker_corners, marker_ids


def auto_detect_charuco(
    gray: np.ndarray,
    board_cols: int,
    board_rows: int,
    square_size_mm: float,
    marker_size_mm: float,
    candidate_dict_names: list[str] | None = None,
):
    best: tuple[int, str, Any, np.ndarray | None, np.ndarray | None, list[np.ndarray], np.ndarray | None] | None = None
    for dict_name in candidate_dict_names or ARUCO_DICT_NAMES:
        board = build_charuco_board(board_cols, board_rows, square_size_mm, marker_size_mm, dict_name)
        found, charuco_corners, charuco_ids, marker_corners, marker_ids = detect_charuco(gray, board)
        score = 0 if charuco_ids is None else int(len(charuco_ids))
        if best is None or score > best[0]:
            best = (score, dict_name, board, charuco_corners, charuco_ids, marker_corners, marker_ids)
        if found and score >= 12:
            break
    if best is None:
        return False, None, None, None, None, None, None
    score, dict_name, board, charuco_corners, charuco_ids, marker_corners, marker_ids = best
    found = charuco_corners is not None and charuco_ids is not None and score >= 6
    return found, dict_name, board, charuco_corners, charuco_ids, marker_corners, marker_ids


def match_charuco_image_points(board, charuco_corners: np.ndarray, charuco_ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    object_points, image_points = board.matchImagePoints(charuco_corners, charuco_ids)
    return (
        object_points.reshape(-1, 3).astype(np.float32),
        image_points.reshape(-1, 2).astype(np.float32),
    )


def solve_pnp(
    corners: np.ndarray,
    object_points: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    object_points = np.asarray(object_points, dtype=np.float32)
    corners = np.asarray(corners, dtype=np.float32)
    is_planar = np.ptp(object_points[:, 2]) < 1e-6

    if is_planar and len(object_points) >= 4:
        ok, rvecs, tvecs, reproj = cv2.solvePnPGeneric(
            object_points,
            corners,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_IPPE,
        )
        if ok and rvecs:
            best: tuple[float, np.ndarray, np.ndarray] | None = None
            for idx, (rvec, tvec) in enumerate(zip(rvecs, tvecs)):
                rot, _ = cv2.Rodrigues(rvec)
                pts_cam = (rot @ object_points.T).T + tvec.reshape(1, 3)
                if np.any(pts_cam[:, 2] <= 0.0):
                    continue
                score = float(reproj[idx][0]) if reproj is not None else float(np.mean(pts_cam[:, 2]))
                if best is None or score < best[0]:
                    best = (score, rvec, tvec)
            if best is not None:
                rvec, tvec = best[1], best[2]
                if hasattr(cv2, "solvePnPRefineLM"):
                    rvec, tvec = cv2.solvePnPRefineLM(
                        object_points,
                        corners,
                        camera_matrix,
                        dist_coeffs,
                        rvec,
                        tvec,
                    )
                return rvec, tvec

    ok, rvec, tvec = cv2.solvePnP(
        object_points,
        corners,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        raise RuntimeError("solvePnP failed")
    if hasattr(cv2, "solvePnPRefineLM"):
        rvec, tvec = cv2.solvePnPRefineLM(
            object_points,
            corners,
            camera_matrix,
            dist_coeffs,
            rvec,
            tvec,
        )
    return rvec, tvec


def reprojection_error(
    object_points: np.ndarray,
    corners: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> float:
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, dist_coeffs)
    return float(np.sqrt(np.mean(np.sum((projected.reshape(-1, 2) - corners.reshape(-1, 2)) ** 2, axis=1))))


def intrinsics_to_matrix(intrinsics: dict[str, float]) -> np.ndarray:
    return np.array(
        [
            [intrinsics["fx"], 0.0, intrinsics["ppx"]],
            [0.0, intrinsics["fy"], intrinsics["ppy"]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def intrinsics_from_rs(intrinsics: Any) -> dict[str, Any]:
    return {
        "width": int(intrinsics.width),
        "height": int(intrinsics.height),
        "fx": float(intrinsics.fx),
        "fy": float(intrinsics.fy),
        "ppx": float(intrinsics.ppx),
        "ppy": float(intrinsics.ppy),
        "coeffs": [float(v) for v in intrinsics.coeffs],
        "model": str(intrinsics.model),
    }


def rt_to_matrix(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    rot, _ = cv2.Rodrigues(rvec)
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = rot
    mat[:3, 3] = tvec.reshape(3)
    return mat


def load_tcp_offset(path: Path | None) -> list[float] | None:
    if path is None:
        return None
    data = load_yaml(path)
    if isinstance(data, dict):
        if "pose6" in data:
            data = data["pose6"]
        elif "tcp_offset_pose" in data:
            data = data["tcp_offset_pose"]
    if not isinstance(data, list) or len(data) != 6:
        raise ValueError(f"TCP offset file {path} must contain a 6-element list or pose6 field")
    return [float(v) for v in data]


def require_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def camera_matrix_and_dist_from_manifest(manifest: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    intrinsics = manifest["camera_intrinsics"]
    return intrinsics_to_matrix(intrinsics), np.array(intrinsics["coeffs"], dtype=np.float64)
