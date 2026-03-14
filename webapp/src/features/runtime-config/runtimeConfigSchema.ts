import type { RuntimeConfig } from "../../types/domain";

export const DEFAULT_RUNTIME_CONFIG: RuntimeConfig = {
  hover_height_m: 0.2,
  grasp_z_offset_m: 0.18,
  drop_hover_z_m: 0.25,
  drop_z_m: 0.15,
  follow_rate_hz: 10,
  base_offset_m: [0, 0, 0],
  pose_rpy_deg: [90, -90, 0],
  target_labels: ["bottle", "cup"],
};
