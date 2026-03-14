import type { DetectionState, DropPosesResponse, RuntimeConfig, SystemStatus, TaskPosesResponse } from "../types/domain";

export const MOCK_STATUS: SystemStatus = {
  can_up: true,
  robot_connected: true,
  camera_ready: true,
  model_ready: true,
  busy: false,
  current_mode: "idle",
  current_step: null,
  calibration_file: "/home/robot/project/sort_trash/data/calib_run_02/calibration_result.yaml",
  safety: { min_z_m: 0.1 },
};

export const MOCK_DETECTION: DetectionState = {
  target: {
    class_name: "bottle",
    target_name: "bottle",
    confidence: 0.91,
    camera_xyz_m: [0.122, -0.031, 0.847],
    base_xyz_m: [-0.341, 0.182, 0.064],
    hover_pose: [-0.341, 0.182, 0.264, 1.57, -1.57, 0],
    pregrasp_pose: [-0.341, 0.182, 0.244, 1.57, -1.57, 0],
    drop_hover_pose: [-0.309, -0.371, 0.25, 1.57, -1.57, 0],
  },
  top_detections: [
    { class_name: "bottle", confidence: 0.91 },
    { class_name: "cup", confidence: 0.23 },
  ],
};

export const MOCK_RUNTIME_CONFIG: RuntimeConfig = {
  hover_height_m: 0.2,
  grasp_z_offset_m: 0.18,
  drop_hover_z_m: 0.25,
  drop_z_m: 0.15,
  follow_rate_hz: 10,
  base_offset_m: [-0.1, 0, 0],
  pose_rpy_deg: [90, -90, 0],
  target_labels: ["bottle", "cup"],
};

export const MOCK_TASK_POSES: TaskPosesResponse = {
  task_poses: {
    home: { pose: [0, -0.0235, 0.718, 1.3321, 1.5707, -0.2386] },
    work: { pose: [-0.2865, -0.0263, 0.4352, 1.6405, -0.9028, -0.0461] },
    standby: { pose: [-0.308, 0.052, 0.41, 1.57, -1.57, 0] },
  },
};

export const MOCK_DROP_POSES: DropPosesResponse = {
  drop_poses: {
    bottle: { xy: [-0.308629, -0.371221] },
    cup: { xy: [-0.058509, -0.34524] },
  },
};

export const MOCK_VIDEO_PLACEHOLDER =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
    <rect width="1280" height="720" fill="#020617"/>
    <rect x="160" y="120" width="960" height="480" rx="16" fill="#0f172a" stroke="#164e63" stroke-width="4"/>
    <rect x="540" y="210" width="180" height="260" fill="none" stroke="#06b6d4" stroke-width="4"/>
    <rect x="540" y="182" width="180" height="28" fill="#06b6d4"/>
    <text x="552" y="201" font-family="monospace" font-size="18" font-weight="700" fill="#020617">BOTTLE 91%</text>
    <text x="60" y="70" font-family="monospace" font-size="28" fill="#67e8f9">MOCK VIDEO STREAM</text>
    <text x="60" y="108" font-family="monospace" font-size="18" fill="#94a3b8">Replace /api/video.mjpg with real MJPEG source.</text>
  </svg>
`);
