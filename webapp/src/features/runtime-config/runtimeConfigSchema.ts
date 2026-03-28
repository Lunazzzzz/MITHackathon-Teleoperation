import type { RuntimeConfig } from "../../types/domain";

export const DEFAULT_RUNTIME_CONFIG: RuntimeConfig = {
  hover_height_m: 0.15,
  grasp_z_offset_m: 0.1,
  drop_hover_z_m: 0.25,
  drop_z_m: 0.15,
  follow_rate_hz: 10,
  imgsz: 960,
  base_offset_m: [0.13, 0, 0],
  pose_rpy_deg: [90.1, -3.89, -1.41],
  rotate_inference_modes: ["none", "cw90", "ccw90"],
  target_labels: ["bottle", "cup"],
};
