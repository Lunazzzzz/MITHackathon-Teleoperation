import type { DropPosesResponse, SystemStatus, TaskPosesResponse } from "../types/domain";

export function hasRequiredTaskPoses(taskPoses: TaskPosesResponse | null) {
  const poses = taskPoses?.task_poses ?? {};
  return Boolean(poses.home && poses.work && poses.standby);
}

export function hasRequiredDropPoses(dropPoses: DropPosesResponse | null) {
  const poses = dropPoses?.drop_poses ?? {};
  return Boolean(poses.bottle && poses.cup);
}

export function listMissingRequirements(taskPoses: TaskPosesResponse | null, dropPoses: DropPosesResponse | null) {
  const missing: string[] = [];
  const tasks = taskPoses?.task_poses ?? {};
  const drops = dropPoses?.drop_poses ?? {};
  if (!tasks.home) missing.push("缺少 Home");
  if (!tasks.work) missing.push("缺少 Work");
  if (!tasks.standby) missing.push("缺少 Standby");
  if (!drops.bottle) missing.push("缺少 Bottle Drop");
  if (!drops.cup) missing.push("缺少 Cup Drop");
  return missing;
}

export function canRunFakeGrasp(
  status: SystemStatus | null,
  taskPoses: TaskPosesResponse | null,
  dropPoses: DropPosesResponse | null,
) {
  if (!status) return false;
  if (!status.can_up || status.busy) return false;
  if (status.current_mode === "following" || status.current_mode === "running_fake_cycle") return false;
  return hasRequiredTaskPoses(taskPoses) && hasRequiredDropPoses(dropPoses);
}
