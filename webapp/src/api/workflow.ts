import { apiRequest } from "./client";
import type { RuntimeConfig } from "../types/domain";

export function runFakeGrasp(config: RuntimeConfig) {
  return apiRequest<{ started: boolean }>("/api/workflow/fake-grasp", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function stopWorkflow() {
  return apiRequest<{ stopped: boolean }>("/api/workflow/stop", {
    method: "POST",
  });
}

export function startFollow(config: RuntimeConfig) {
  return apiRequest<{ started: boolean }>("/api/follow/start", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function stopFollow() {
  return apiRequest<{ stopped: boolean }>("/api/follow/stop", {
    method: "POST",
  });
}

export function moveHome() {
  return apiRequest<{ moved: string }>("/api/robot/move-home", { method: "POST" });
}

export function moveWork() {
  return apiRequest<{ moved: string }>("/api/robot/move-work", { method: "POST" });
}

export function moveStandby() {
  return apiRequest<{ moved: string }>("/api/robot/move-standby", { method: "POST" });
}
