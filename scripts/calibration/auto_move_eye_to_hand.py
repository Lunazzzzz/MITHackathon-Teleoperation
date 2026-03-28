#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Sequence

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
CONTROL_DIR = SCRIPTS_DIR / "control"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(CONTROL_DIR))
from _local_sdk import prefer_local_pyagxarm

prefer_local_pyagxarm(__file__)

from control._safety import MIN_TOOL_Z_M, check_pose_min_z
from control.sweep_cartesian_pose import angular_delta_rad, monitor_pose, pose_to_mm_deg, print_pose, send_pose


DEFAULT_CENTER_POSE = [
    -0.502692,
    -0.047758,
    0.402391,
    math.radians(97.133),
    math.radians(35.377),
    math.radians(-15.259),
]
DEFAULT_CAMERA_POINT = [-0.77885629, 0.05961147, 0.81929908]
DEFAULT_BOARD_UP_LOCAL_AXIS = [-0.66595979, 0.74593036, -0.00924392]
MIN_CALIBRATION_Z_M = max(MIN_TOOL_Z_M, 0.15)
BOARD_SIZE_M = 0.20
BOARD_HALF_WIDTH_M = BOARD_SIZE_M * 0.5
BOARD_HEIGHT_M = BOARD_SIZE_M


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move the robot through a conservative eye-to-hand calibration pose sequence around "
            "a known camera-facing center pose. Tool orientation stays fixed while positions are sampled "
            "inside a bounded horizontal/vertical angular sector."
        )
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN channel, e.g. can0")
    parser.add_argument("--robot", default="nero", help="Robot name passed into pyAgxArm (default: nero)")
    parser.add_argument(
        "--center-pose",
        nargs=6,
        type=float,
        default=DEFAULT_CENTER_POSE,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        help=(
            "Center flange pose [x y z roll pitch yaw]. "
            "Default uses the sample camera-facing pose. Units: meters + radians unless --mm/--degrees."
        ),
    )
    parser.add_argument(
        "--camera-point",
        nargs=3,
        type=float,
        default=DEFAULT_CAMERA_POINT,
        metavar=("X", "Y", "Z"),
        help="Estimated camera point [x y z]. Default is fitted from the 4 camera-facing samples.",
    )
    parser.add_argument("--camera-point-mm", action="store_true", help="Interpret --camera-point as millimeters.")
    parser.add_argument("--mm", action="store_true", help="Interpret center pose x/y/z as millimeters.")
    parser.add_argument("--degrees", action="store_true", help="Interpret center pose roll/pitch/yaw as degrees.")
    parser.add_argument(
        "--elevation-min-deg",
        type=float,
        default=0.0,
        help="Minimum vertical projection angle relative to the base horizontal plane. Default: 0.",
    )
    parser.add_argument(
        "--elevation-max-deg",
        type=float,
        default=45.0,
        help="Maximum vertical projection angle relative to the base horizontal plane. Default: 45.",
    )
    parser.add_argument(
        "--azimuth-min-deg",
        type=float,
        default=-45.0,
        help="Minimum horizontal projection angle relative to the base forward direction. Default: -45.",
    )
    parser.add_argument(
        "--azimuth-max-deg",
        type=float,
        default=45.0,
        help="Maximum horizontal projection angle relative to the base forward direction. Default: 45.",
    )
    parser.add_argument(
        "--radius-minus-mm",
        type=float,
        default=40.0,
        help="How much closer than the center radius to sample, in mm. Default: 40.",
    )
    parser.add_argument(
        "--radius-plus-mm",
        type=float,
        default=60.0,
        help="How much farther than the center radius to sample, in mm. Default: 60.",
    )
    parser.add_argument(
        "--max-xy-offset-mm",
        type=float,
        default=220.0,
        help="Maximum XY offset from the center pose before a target is compressed inward. Default: 220.",
    )
    parser.add_argument(
        "--max-upward-tilt-deg",
        type=float,
        default=45.0,
        help="Maximum tilt away from straight up when orienting the tool. Default: 45.",
    )
    parser.add_argument(
        "--transition-lift-mm",
        type=float,
        default=80.0,
        help="Deprecated in unsafe direct mode. Kept for CLI compatibility.",
    )
    parser.add_argument(
        "--dwell-seconds",
        type=float,
        default=5.0,
        help="Seconds to wait after each pose is reached. Default: 5.0.",
    )
    parser.add_argument(
        "--speed-percent",
        type=int,
        default=10,
        help="Speed percent [0..100]. Default: 10 for cautious motion.",
    )
    parser.add_argument(
        "--send-order",
        default="mode_target_mode",
        choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"],
        help="How to send the Cartesian command. Default: mode_target_mode.",
    )
    parser.add_argument(
        "--mode-resend",
        type=int,
        default=3,
        help="How many times to resend the motion mode command. Default: 3.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=6.0,
        help="Seconds to monitor each pose after sending. Default: 6.0.",
    )
    parser.add_argument(
        "--tolerance-mm",
        type=float,
        default=5.0,
        help="Translation tolerance for considering a pose reached. Default: 5 mm.",
    )
    parser.add_argument(
        "--tolerance-deg",
        type=float,
        default=3.0,
        help="Rotation tolerance for considering a pose reached. Default: 3 deg.",
    )
    parser.add_argument(
        "--min-motion-mm",
        type=float,
        default=4.0,
        help="Consider translation motion detected above this threshold. Default: 4 mm.",
    )
    parser.add_argument(
        "--min-rotation-deg",
        type=float,
        default=2.0,
        help="Consider rotation motion detected above this threshold. Default: 2 deg.",
    )
    parser.add_argument(
        "--max-start-distance-mm",
        type=float,
        default=80.0,
        help="Warn if current pose is farther than this from center pose before the initial move. Default: 80 mm.",
    )
    parser.add_argument(
        "--max-start-rotation-deg",
        type=float,
        default=12.0,
        help="Warn if current orientation differs from center by more than this before the initial move. Default: 12 deg.",
    )
    parser.add_argument(
        "--no-normal-mode",
        action="store_true",
        help="Do not call robot.set_normal_mode() before enabling/moving.",
    )
    parser.add_argument(
        "--no-enable",
        action="store_true",
        help="Do not call robot.enable() before moving.",
    )
    parser.add_argument(
        "--go",
        action="store_true",
        help="Actually execute the motion sequence. Without this flag the script only prints the plan.",
    )
    return parser.parse_args()


def to_meters_if_needed(pose: Sequence[float], mm: bool) -> list[float]:
    out = [float(v) for v in pose]
    if mm:
        out[0] /= 1000.0
        out[1] /= 1000.0
        out[2] /= 1000.0
    return out


def to_radians_if_needed(pose: Sequence[float], degrees: bool) -> list[float]:
    out = [float(v) for v in pose]
    if degrees:
        out[3] = math.radians(out[3])
        out[4] = math.radians(out[4])
        out[5] = math.radians(out[5])
    return out


def distance_mm(pose_a: Sequence[float], pose_b: Sequence[float]) -> float:
    return math.sqrt(sum(((float(pose_a[i]) - float(pose_b[i])) * 1000.0) ** 2 for i in range(3)))


def rotation_error_deg(pose_a: Sequence[float], pose_b: Sequence[float]) -> float:
    return max(abs(math.degrees(angular_delta_rad(float(pose_a[i]), float(pose_b[i])))) for i in range(3, 6))


def normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(float(v) * float(v) for v in vec))
    if norm <= 1e-9:
        raise ValueError("Cannot normalize a near-zero vector.")
    return [float(v) / norm for v in vec]


def rpy_to_rot(roll: float, pitch: float, yaw: float) -> list[list[float]]:
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def rot_to_rpy(R: Sequence[Sequence[float]]) -> list[float]:
    pitch = math.asin(max(-1.0, min(1.0, -float(R[2][0]))))
    cp = math.cos(pitch)
    if abs(cp) < 1e-9:
        roll = 0.0
        yaw = math.atan2(-float(R[0][1]), float(R[1][1]))
    else:
        roll = math.atan2(float(R[2][1]), float(R[2][2]))
        yaw = math.atan2(float(R[1][0]), float(R[0][0]))
    return [roll, pitch, yaw]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def cross(a: Sequence[float], b: Sequence[float]) -> list[float]:
    ax, ay, az = [float(v) for v in a]
    bx, by, bz = [float(v) for v in b]
    return [
        ay * bz - az * by,
        az * bx - ax * bz,
        ax * by - ay * bx,
    ]


def matmul3(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> list[list[float]]:
    return [
        [
            float(A[i][0]) * float(B[0][j]) + float(A[i][1]) * float(B[1][j]) + float(A[i][2]) * float(B[2][j])
            for j in range(3)
        ]
        for i in range(3)
    ]


def transpose3(A: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(A[j][i]) for j in range(3)] for i in range(3)]


def matvec3(A: Sequence[Sequence[float]], v: Sequence[float]) -> list[float]:
    return [
        float(A[0][0]) * float(v[0]) + float(A[0][1]) * float(v[1]) + float(A[0][2]) * float(v[2]),
        float(A[1][0]) * float(v[0]) + float(A[1][1]) * float(v[1]) + float(A[1][2]) * float(v[2]),
        float(A[2][0]) * float(v[0]) + float(A[2][1]) * float(v[1]) + float(A[2][2]) * float(v[2]),
    ]


def skew(v: Sequence[float]) -> list[list[float]]:
    x, y, z = [float(c) for c in v]
    return [
        [0.0, -z, y],
        [z, 0.0, -x],
        [-y, x, 0.0],
    ]


def identity3() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def add3(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(A[i][j]) + float(B[i][j]) for j in range(3)] for i in range(3)]


def scale3(A: Sequence[Sequence[float]], s: float) -> list[list[float]]:
    return [[float(A[i][j]) * s for j in range(3)] for i in range(3)]


def shortest_arc_rotation(src: Sequence[float], dst: Sequence[float]) -> list[list[float]]:
    src_n = normalize(src)
    dst_n = normalize(dst)
    v = cross(src_n, dst_n)
    s = math.sqrt(dot(v, v))
    c = max(-1.0, min(1.0, dot(src_n, dst_n)))
    if s < 1e-9:
        if c > 0.0:
            return identity3()
        axis = [1.0, 0.0, 0.0] if abs(src_n[0]) < 0.9 else [0.0, 1.0, 0.0]
        axis = normalize([axis[i] - dot(axis, src_n) * src_n[i] for i in range(3)])
        K = skew(axis)
        return add3(identity3(), scale3(matmul3(K, K), 2.0))
    K = skew(v)
    K2 = matmul3(K, K)
    return add3(add3(identity3(), K), scale3(K2, (1.0 - c) / (s * s)))


def clamp_direction_to_upward_cone(direction: Sequence[float], max_upward_tilt_deg: float) -> list[float]:
    direction_n = normalize(direction)
    max_tilt_rad = math.radians(max(0.0, min(89.0, max_upward_tilt_deg)))
    max_horizontal = math.sin(max_tilt_rad)
    min_vertical = math.cos(max_tilt_rad)
    if float(direction_n[2]) >= min_vertical:
        return direction_n

    horizontal_norm = math.sqrt(float(direction_n[0]) ** 2 + float(direction_n[1]) ** 2)
    if horizontal_norm <= 1e-9:
        return [max_horizontal, 0.0, min_vertical]
    scale = max_horizontal / horizontal_norm
    return normalize([float(direction_n[0]) * scale, float(direction_n[1]) * scale, min_vertical])


def derive_board_axes_local(
    reference_pose: Sequence[float],
    camera_point: Sequence[float],
    max_upward_tilt_deg: float,
) -> tuple[list[float], list[float]]:
    board_up_local_axis = normalize(DEFAULT_BOARD_UP_LOCAL_AXIS)
    reference_rot = rpy_to_rot(float(reference_pose[3]), float(reference_pose[4]), float(reference_pose[5]))
    reference_dir_world = clamp_direction_to_upward_cone(
        [float(camera_point[i]) - float(reference_pose[i]) for i in range(3)],
        max_upward_tilt_deg,
    )
    reference_dir_local = matvec3(transpose3(reference_rot), reference_dir_world)
    board_normal_local_axis = [
        reference_dir_local[i] - dot(reference_dir_local, board_up_local_axis) * board_up_local_axis[i]
        for i in range(3)
    ]
    if math.sqrt(dot(board_normal_local_axis, board_normal_local_axis)) <= 1e-9:
        fallback = [1.0, 0.0, 0.0] if abs(board_up_local_axis[0]) < 0.9 else [0.0, 1.0, 0.0]
        board_normal_local_axis = cross(board_up_local_axis, fallback)
    board_normal_local_axis = normalize(board_normal_local_axis)
    board_side_local_axis = normalize(cross(board_normal_local_axis, board_up_local_axis))
    return board_up_local_axis, board_side_local_axis


def board_min_z_m(
    pose: Sequence[float],
    board_up_local_axis: Sequence[float],
    board_side_local_axis: Sequence[float],
) -> float:
    rot = rpy_to_rot(float(pose[3]), float(pose[4]), float(pose[5]))
    board_up_world = matvec3(rot, board_up_local_axis)
    board_side_world = matvec3(rot, board_side_local_axis)
    z_values = [float(pose[2])]
    for side_sign in (-1.0, 1.0):
        for up_fraction in (0.0, 1.0):
            z_values.append(
                float(pose[2])
                + side_sign * BOARD_HALF_WIDTH_M * float(board_side_world[2])
                + up_fraction * BOARD_HEIGHT_M * float(board_up_world[2])
            )
    return min(z_values)


def check_board_clearance(
    pose: Sequence[float],
    board_up_local_axis: Sequence[float],
    board_side_local_axis: Sequence[float],
    label: str,
) -> bool:
    min_board_z_m = board_min_z_m(pose, board_up_local_axis, board_side_local_axis)
    if min_board_z_m >= MIN_CALIBRATION_Z_M:
        return True
    print(
        f"[SAFETY] Refusing to execute {label}: board minimum z={min_board_z_m:.3f} m is below the minimum "
        f"allowed z={MIN_CALIBRATION_Z_M:.3f} m."
    )
    return False


def orient_pose_to_camera(
    target_xyz: Sequence[float],
    camera_point: Sequence[float],
    reference_pose: Sequence[float],
    max_upward_tilt_deg: float,
) -> list[float]:
    reference_rot = rpy_to_rot(float(reference_pose[3]), float(reference_pose[4]), float(reference_pose[5]))
    reference_dir = clamp_direction_to_upward_cone(
        [float(camera_point[i]) - float(reference_pose[i]) for i in range(3)],
        max_upward_tilt_deg,
    )
    target_dir = clamp_direction_to_upward_cone(
        [float(camera_point[i]) - float(target_xyz[i]) for i in range(3)],
        max_upward_tilt_deg,
    )
    transport = shortest_arc_rotation(reference_dir, target_dir)
    target_rot = matmul3(transport, reference_rot)
    return [float(target_xyz[0]), float(target_xyz[1]), float(target_xyz[2]), *rot_to_rpy(target_rot)]


def pose_position_to_sector_deg(pose: Sequence[float]) -> tuple[float, float, float]:
    x_m, y_m, z_m = [float(v) for v in pose[:3]]
    radius_m = math.sqrt(x_m * x_m + y_m * y_m + z_m * z_m)
    planar_m = math.sqrt(x_m * x_m + y_m * y_m)
    azimuth_deg = math.degrees(math.atan2(y_m, -x_m))
    elevation_deg = math.degrees(math.atan2(z_m, planar_m))
    return radius_m, azimuth_deg, elevation_deg


def sector_deg_to_position(radius_m: float, azimuth_deg: float, elevation_deg: float) -> list[float]:
    azimuth_rad = math.radians(azimuth_deg)
    elevation_rad = math.radians(elevation_deg)
    planar_m = radius_m * math.cos(elevation_rad)
    x_m = -planar_m * math.cos(azimuth_rad)
    y_m = planar_m * math.sin(azimuth_rad)
    z_m = radius_m * math.sin(elevation_rad)
    return [x_m, y_m, z_m]


def min_safe_elevation_deg(radius_m: float) -> float:
    if radius_m <= MIN_CALIBRATION_Z_M:
        return 90.0
    return math.degrees(math.asin(MIN_CALIBRATION_Z_M / radius_m))


def check_calibration_pose_min_z(pose: Sequence[float], label: str) -> bool:
    return check_pose_min_z(list(pose), label, min_z_m=MIN_CALIBRATION_Z_M)


def translation_delta_mm(pose_a: Sequence[float], pose_b: Sequence[float]) -> float:
    return math.sqrt(sum(((float(pose_a[i]) - float(pose_b[i])) * 1000.0) ** 2 for i in range(3)))


def xy_delta_mm(pose_a: Sequence[float], pose_b: Sequence[float]) -> float:
    return math.sqrt(sum(((float(pose_a[i]) - float(pose_b[i])) * 1000.0) ** 2 for i in range(2)))


def clamp_xy_offset_from_center(
    target_xyz: Sequence[float],
    center_pose: Sequence[float],
    max_xy_offset_mm: float,
) -> tuple[list[float], float, bool]:
    dx = float(target_xyz[0]) - float(center_pose[0])
    dy = float(target_xyz[1]) - float(center_pose[1])
    offset_mm = math.hypot(dx, dy) * 1000.0
    if offset_mm <= max_xy_offset_mm or offset_mm <= 1e-9:
        return [float(target_xyz[0]), float(target_xyz[1]), float(target_xyz[2])], offset_mm, False

    scale = max_xy_offset_mm / offset_mm
    return [
        float(center_pose[0]) + dx * scale,
        float(center_pose[1]) + dy * scale,
        float(target_xyz[2]),
    ], max_xy_offset_mm, True


def orientation_delta_deg(pose_a: Sequence[float], pose_b: Sequence[float]) -> float:
    return max(abs(math.degrees(angular_delta_rad(float(pose_a[i]), float(pose_b[i])))) for i in range(3, 6))


def build_transition_waypoints(
    start_pose: Sequence[float],
    target_pose: Sequence[float],
    center_pose: Sequence[float],
    transition_lift_mm: float,
) -> list[tuple[str, list[float]]]:
    travel_z_m = max(
        float(start_pose[2]),
        float(target_pose[2]),
        float(center_pose[2]) + transition_lift_mm / 1000.0,
    )
    waypoints: list[tuple[str, list[float]]] = []
    current = [float(v) for v in start_pose]

    retreat_pose = [float(center_pose[0]), float(center_pose[1]), current[2], current[3], current[4], current[5]]
    if xy_delta_mm(current, retreat_pose) > 1.0:
        waypoints.append(("retreat_xy", retreat_pose))
        current = [float(v) for v in retreat_pose]

    lift_pose = [current[0], current[1], travel_z_m, current[3], current[4], current[5]]
    if abs(lift_pose[2] - current[2]) * 1000.0 > 1.0:
        waypoints.append(("lift", lift_pose))
        current = [float(v) for v in lift_pose]

    rotate_pose = [current[0], current[1], current[2], float(target_pose[3]), float(target_pose[4]), float(target_pose[5])]
    if orientation_delta_deg(current, rotate_pose) > 1.0:
        waypoints.append(("rotate", rotate_pose))
        current = [float(v) for v in rotate_pose]

    cruise_pose = [float(target_pose[0]), float(target_pose[1]), current[2], current[3], current[4], current[5]]
    if xy_delta_mm(current, cruise_pose) > 1.0:
        waypoints.append(("cruise_xy", cruise_pose))
        current = [float(v) for v in cruise_pose]

    final_pose = [float(v) for v in target_pose]
    if translation_delta_mm(current, final_pose) > 1.0 or orientation_delta_deg(current, final_pose) > 1.0:
        waypoints.append(("descend", final_pose))

    return waypoints


def execute_pose(
    robot: object,
    pose: Sequence[float],
    *,
    pose_label: str,
    board_up_local_axis: Sequence[float],
    board_side_local_axis: Sequence[float],
    args: argparse.Namespace,
) -> tuple[bool, list[float] | None]:
    if not check_calibration_pose_min_z(pose, pose_label):
        print("Target pose violates the strict z safety limit. Sequence stopped.")
        return False, None
    if not check_board_clearance(pose, board_up_local_axis, board_side_local_axis, pose_label):
        print("Target pose violates the board clearance safety limit. Sequence stopped.")
        return False, None
    send_pose(robot, pose, args.send_order, args.mode_resend)
    monitor = monitor_pose(
        robot=robot,
        target_pose=pose,
        wait_seconds=args.wait_seconds,
        tolerance_mm=args.tolerance_mm,
        tolerance_deg=args.tolerance_deg,
        min_motion_mm=args.min_motion_mm,
        min_rotation_deg=args.min_rotation_deg,
    )
    if monitor["last_pose"] is not None:
        print_pose("Last flange pose", monitor["last_pose"])
    if not monitor["success"]:
        print("Motion did not converge to the requested pose. Sequence stopped.")
        return False, monitor["last_pose"]
    return True, monitor["last_pose"]


def execute_transition(
    robot: object,
    start_pose: Sequence[float],
    target_pose: Sequence[float],
    center_pose: Sequence[float],
    *,
    transition_name: str,
    args: argparse.Namespace,
) -> tuple[bool, list[float] | None]:
    waypoints = build_transition_waypoints(start_pose, target_pose, center_pose, args.transition_lift_mm)
    if not waypoints:
        print("Already at target pose; no transition waypoints needed.")
        return True, [float(v) for v in start_pose]

    print(
        f"Safe transition plan: {len(waypoints)} waypoint(s), "
        f"lift_margin={args.transition_lift_mm:.1f} mm"
    )
    current_pose = [float(v) for v in start_pose]
    for idx, (stage, waypoint) in enumerate(waypoints, start=1):
        print(f"  -> {transition_name} step {idx}/{len(waypoints)} [{stage}]")
        print_pose("     command", waypoint)
        ok, last_pose = execute_pose(robot, waypoint, pose_label=f"{transition_name}:{stage}", args=args)
        if last_pose is not None:
            current_pose = [float(v) for v in last_pose]
        else:
            current_pose = [float(v) for v in waypoint]
        if not ok:
            return False, current_pose
    return True, current_pose


def build_sequence(
    center_pose: Sequence[float],
    camera_point: Sequence[float],
    max_upward_tilt_deg: float,
    board_up_local_axis: Sequence[float],
    board_side_local_axis: Sequence[float],
    elevation_min_deg: float,
    elevation_max_deg: float,
    azimuth_min_deg: float,
    azimuth_max_deg: float,
    radius_minus_mm: float,
    radius_plus_mm: float,
    max_xy_offset_mm: float,
) -> list[dict[str, object]]:
    center_radius_m, center_azimuth_deg, center_elevation_deg = pose_position_to_sector_deg(center_pose)
    near_radius_m = max(MIN_CALIBRATION_Z_M + 0.02, center_radius_m - radius_minus_mm / 1000.0)
    far_radius_m = center_radius_m + radius_plus_mm / 1000.0

    low_elevation_deg = max((max(elevation_min_deg, min_safe_elevation_deg(near_radius_m)) + center_elevation_deg) * 0.5, elevation_min_deg)
    mid_elevation_deg = center_elevation_deg
    high_elevation_deg = elevation_max_deg

    azimuth_levels = [
        ("left", azimuth_min_deg),
        ("left_mid", (azimuth_min_deg + center_azimuth_deg) * 0.5),
        ("center", center_azimuth_deg),
        ("right_mid", (center_azimuth_deg + azimuth_max_deg) * 0.5),
        ("right", azimuth_max_deg),
    ]
    row_specs = [
        ("low", near_radius_m, low_elevation_deg),
        ("mid", center_radius_m, mid_elevation_deg),
        ("high", far_radius_m, high_elevation_deg),
    ]
    point_map: dict[str, tuple[float, float, float]] = {}
    for row_name, radius_m, elevation_deg in row_specs:
        for col_name, azimuth_deg in azimuth_levels:
            point_map[f"{row_name}_{col_name}"] = (radius_m, azimuth_deg, elevation_deg)

    ordered_labels = [
        ("center", "mid_center"),
        ("mid_left_mid", "mid_left_mid"),
        ("mid_left", "mid_left"),
        ("mid_right_mid", "mid_right_mid"),
        ("mid_right", "mid_right"),
        ("high_right", "high_right"),
        ("high_right_mid", "high_right_mid"),
        ("high_center", "high_center"),
        ("high_left_mid", "high_left_mid"),
        ("high_left", "high_left"),
        ("low_left", "low_left"),
        ("low_left_mid", "low_left_mid"),
        ("low_center", "low_center"),
        ("low_right_mid", "low_right_mid"),
        ("low_right", "low_right"),
    ]

    sequence: list[dict[str, object]] = []
    for label, key in ordered_labels:
        radius_m, azimuth_deg, elevation_deg = point_map[key]
        target_xyz = sector_deg_to_position(radius_m, azimuth_deg, elevation_deg)
        target_xyz, xy_offset_mm, xy_compressed = clamp_xy_offset_from_center(target_xyz, center_pose, max_xy_offset_mm)
        pose = orient_pose_to_camera(target_xyz, camera_point, center_pose, max_upward_tilt_deg)
        if not check_calibration_pose_min_z(pose, f"planned_pose:{label}"):
            raise ValueError(f"Planned pose '{label}' violates the strict z safety limit.")
        if not check_board_clearance(pose, board_up_local_axis, board_side_local_axis, f"planned_pose:{label}"):
            raise ValueError(f"Planned pose '{label}' violates the board clearance safety limit.")
        sequence.append(
            {
                "label": label,
                "sector_deg": {
                    "azimuth_deg": azimuth_deg,
                    "elevation_deg": elevation_deg,
                    "radius_mm": radius_m * 1000.0,
                },
                "xy_offset_mm": xy_offset_mm,
                "xy_compressed": xy_compressed,
                "board_min_z_mm": board_min_z_m(pose, board_up_local_axis, board_side_local_axis) * 1000.0,
                "pose": pose,
            }
        )
    return sequence


def build_robot(channel: str, robot_name: str):
    from pyAgxArm import AgxArmFactory, create_agx_arm_config

    cfg = create_agx_arm_config(robot=robot_name, comm="can", channel=channel, interface="socketcan")
    robot = AgxArmFactory.create_arm(cfg)
    robot.connect()
    return robot


def read_flange_pose(robot: object, timeout_s: float = 2.0) -> list[float]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        msg = robot.get_flange_pose()
        if msg is not None:
            return [float(v) for v in msg.msg]
        time.sleep(0.05)
    raise RuntimeError("Failed to read current flange pose from the robot.")


def main() -> int:
    args = parse_args()
    center_pose = to_radians_if_needed(to_meters_if_needed(args.center_pose, args.mm), args.degrees)
    camera_point = to_meters_if_needed(args.camera_point, args.camera_point_mm)
    board_up_local_axis, board_side_local_axis = derive_board_axes_local(center_pose, camera_point, args.max_upward_tilt_deg)
    center_radius_m, center_azimuth_deg, center_elevation_deg = pose_position_to_sector_deg(center_pose)
    if not args.elevation_min_deg <= center_elevation_deg <= args.elevation_max_deg:
        raise SystemExit(
            f"Center pose elevation={center_elevation_deg:.3f} deg is outside the configured vertical range "
            f"[{args.elevation_min_deg:.3f}, {args.elevation_max_deg:.3f}] deg."
        )
    if not args.azimuth_min_deg <= center_azimuth_deg <= args.azimuth_max_deg:
        raise SystemExit(
            f"Center pose azimuth={center_azimuth_deg:.3f} deg is outside the configured horizontal range "
            f"[{args.azimuth_min_deg:.3f}, {args.azimuth_max_deg:.3f}] deg."
        )
    sequence = build_sequence(
        center_pose,
        camera_point,
        args.max_upward_tilt_deg,
        board_up_local_axis,
        board_side_local_axis,
        args.elevation_min_deg,
        args.elevation_max_deg,
        args.azimuth_min_deg,
        args.azimuth_max_deg,
        args.radius_minus_mm,
        args.radius_plus_mm,
        args.max_xy_offset_mm,
    )

    print_pose("Center pose", center_pose)
    print(
        "Center sector: "
        f"radius={center_radius_m * 1000.0:.1f} mm, "
        f"azimuth={center_azimuth_deg:.3f} deg, "
        f"elevation={center_elevation_deg:.3f} deg"
    )
    print(f"Strict z safety limit: {MIN_CALIBRATION_Z_M * 1000.0:.0f} mm above the base plane")
    print(f"Unsafe direct mode: enabled")
    print(f"Upward tilt limit: {args.max_upward_tilt_deg:.1f} deg from straight up")
    print(f"XY offset limit from center: {args.max_xy_offset_mm:.1f} mm")
    print("Board model: 200x200 mm, lower-edge midpoint attached to tool")
    print(
        "Estimated camera point: "
        f"x={camera_point[0] * 1000.0:.1f} y={camera_point[1] * 1000.0:.1f} z={camera_point[2] * 1000.0:.1f} mm"
    )
    print("Planned sequence:")
    for idx, item in enumerate(sequence, start=1):
        sector_deg = item["sector_deg"]
        pose = item["pose"]
        print(
            f"  {idx:02d}. {item['label']} sector_deg={sector_deg} "
            f"xy_offset_mm={item['xy_offset_mm']:.1f} "
            f"compressed={item['xy_compressed']} "
            f"board_min_z_mm={item['board_min_z_mm']:.1f}"
        )
        print_pose("      pose", pose)

    if not args.go:
        print("Dry run: pass --go to execute the motion sequence.")
        return 0

    robot = build_robot(args.channel, args.robot)
    current_pose = read_flange_pose(robot)
    print_pose("Current flange pose", current_pose)

    start_translation_mm = distance_mm(current_pose, center_pose)
    start_rotation_deg = rotation_error_deg(current_pose, center_pose)
    print(
        "Current vs center: "
        f"translation={start_translation_mm:.2f} mm, rotation={start_rotation_deg:.2f} deg"
    )
    if start_translation_mm > args.max_start_distance_mm or start_rotation_deg > args.max_start_rotation_deg:
        print(
            "Warning: current pose is relatively far from the center pose. "
            "The script will still move to the initial center pose automatically."
        )

    if not args.no_normal_mode and hasattr(robot, "set_normal_mode"):
        robot.set_normal_mode()
        print("set_normal_mode sent.")

    if not args.no_enable:
        ok = robot.enable()
        print("enable (immediate):", ok)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                states = robot.get_joints_enable_status_list()
            except Exception:
                states = None
            if states is not None and all(states):
                print("enabled joints:", states)
                break
            time.sleep(0.05)

    robot.set_speed_percent(args.speed_percent)
    print(f"Speed percent set to {args.speed_percent}.")

    print()
    print("=== Initial move: center ===")
    print_pose("Target pose", center_pose)
    ok, current_pose = execute_pose(
        robot,
        center_pose,
        pose_label="initial_center",
        board_up_local_axis=board_up_local_axis,
        board_side_local_axis=board_side_local_axis,
        args=args,
    )
    if not ok:
        print("Failed to reach the initial center pose. Sequence stopped.")
        return 1

    for seq_idx, item in enumerate(sequence, start=1):
        target_pose = item["pose"]
        print()
        print(f"=== Sequence pose {seq_idx}/{len(sequence)}: {item['label']} ===")
        print_pose("Target pose", target_pose)
        if seq_idx == 1 and item["label"] == "center":
            print("Already at center after the initial move; skipping duplicate command.")
        else:
            ok, current_pose = execute_pose(
                robot,
                target_pose,
                pose_label=f"sequence_pose:{item['label']}",
                board_up_local_axis=board_up_local_axis,
                board_side_local_axis=board_side_local_axis,
                args=args,
            )
            if not ok:
                return 1
        if current_pose is None:
            current_pose = [float(v) for v in target_pose]

        print(f"Holding for {args.dwell_seconds:.1f} seconds for manual calibration work.")
        time.sleep(max(0.0, args.dwell_seconds))

    print()
    print("Calibration motion sequence finished successfully.")
    final_pose = read_flange_pose(robot)
    print_pose("Final flange pose", final_pose)
    print("Final flange pose (mm/deg):", [round(v, 3) for v in pose_to_mm_deg(final_pose)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
