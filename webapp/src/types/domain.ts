export type WorkflowMode =
  | "idle"
  | "detecting"
  | "following"
  | "running_fake_cycle"
  | "recording_pose"
  | "error";

export type WorkflowStep =
  | "home"
  | "work"
  | "target_hover"
  | "pregrasp_10cm"
  | "[FAKE GRASP]"
  | "target_retreat"
  | "standby"
  | "drop_hover"
  | "drop_down"
  | "[FAKE RELEASE]"
  | "drop_retreat"
  | "return_home";

export interface SafetyConfig {
  min_z_m: number;
}

export interface SystemStatus {
  can_up: boolean;
  robot_connected: boolean;
  camera_ready: boolean;
  model_ready: boolean;
  busy: boolean;
  current_mode: WorkflowMode;
  current_step?: WorkflowStep | null;
  calibration_file: string;
  safety: SafetyConfig;
}

export interface DetectionTarget {
  class_name: string;
  target_name: string;
  confidence: number;
  camera_xyz_m: [number, number, number];
  base_xyz_m: [number, number, number];
  hover_pose?: [number, number, number, number, number, number];
  pregrasp_pose?: [number, number, number, number, number, number];
  drop_hover_pose?: [number, number, number, number, number, number];
}

export interface DetectionState {
  target: DetectionTarget | null;
  top_detections?: Array<{ class_name: string; confidence: number }>;
}

export interface RuntimeConfig {
  hover_height_m: number;
  grasp_z_offset_m: number;
  drop_hover_z_m: number;
  drop_z_m: number;
  follow_rate_hz: number;
  base_offset_m: [number, number, number];
  pose_rpy_deg: [number, number, number];
  target_labels: string[];
}

export interface TaskPoseEntry {
  pose: [number, number, number, number, number, number];
  frame?: string;
  updated_at?: string;
}

export interface TaskPosesResponse {
  task_poses: Partial<Record<"home" | "work" | "standby", TaskPoseEntry>>;
}

export interface DropPoseEntry {
  xy: [number, number];
  frame?: string;
  updated_at?: string;
}

export interface DropPosesResponse {
  drop_poses: Partial<Record<"bottle" | "cup", DropPoseEntry>>;
}
