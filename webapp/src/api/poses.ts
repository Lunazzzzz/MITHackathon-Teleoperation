import { apiRequest } from "./client";
import type { DropPosesResponse, TaskPosesResponse } from "../types/domain";

export function getTaskPoses() {
  return apiRequest<TaskPosesResponse>("/api/task-poses");
}

export function getDropPoses() {
  return apiRequest<DropPosesResponse>("/api/drop-poses");
}

export function recordTaskPose(name: "home" | "work" | "standby", overwrite = false) {
  return apiRequest<TaskPosesResponse>("/api/task-poses/record", {
    method: "POST",
    body: JSON.stringify({ name, overwrite }),
  });
}

export function recordDropPose(name: "bottle" | "cup", overwrite = false) {
  return apiRequest<DropPosesResponse>("/api/drop-poses/record", {
    method: "POST",
    body: JSON.stringify({ name, overwrite }),
  });
}
