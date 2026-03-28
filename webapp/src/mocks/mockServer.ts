import type { ApiEnvelope } from "../types/api";
import type { DetectionState, DropPosesResponse, RuntimeConfig, SystemStatus, TaskPosesResponse } from "../types/domain";
import { MOCK_DETECTION, MOCK_DROP_POSES, MOCK_RUNTIME_CONFIG, MOCK_STATUS, MOCK_TASK_POSES } from "./fixtures";

let mockStatus: SystemStatus = { ...MOCK_STATUS };
let mockDetection: DetectionState = { ...MOCK_DETECTION };
let mockRuntimeConfig: RuntimeConfig = { ...MOCK_RUNTIME_CONFIG };
let mockTaskPoses: TaskPosesResponse = JSON.parse(JSON.stringify(MOCK_TASK_POSES)) as TaskPosesResponse;
let mockDropPoses: DropPosesResponse = JSON.parse(JSON.stringify(MOCK_DROP_POSES)) as DropPosesResponse;

function ok<T>(data: T, message?: string): ApiEnvelope<T> {
  return { ok: true, message, data };
}

export async function mockRequest<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  const method = (init?.method ?? "GET").toUpperCase();
  const body = init?.body ? JSON.parse(String(init.body)) : null;

  if (path === "/api/status" && method === "GET") {
    return ok(mockStatus) as ApiEnvelope<T>;
  }
  if (path === "/api/detection/state" && method === "GET") {
    return ok(mockDetection) as ApiEnvelope<T>;
  }
  if (path === "/api/runtime-config" && method === "GET") {
    return ok(mockRuntimeConfig) as ApiEnvelope<T>;
  }
  if (path === "/api/task-poses" && method === "GET") {
    return ok(mockTaskPoses) as ApiEnvelope<T>;
  }
  if (path === "/api/drop-poses" && method === "GET") {
    return ok(mockDropPoses) as ApiEnvelope<T>;
  }
  if (path === "/api/config/runtime" && method === "POST") {
    mockRuntimeConfig = { ...mockRuntimeConfig, ...body };
    return ok(mockRuntimeConfig, "Mock runtime config updated.") as ApiEnvelope<T>;
  }
  if (path === "/api/task-poses/record" && method === "POST") {
    const name = body?.name as "home" | "work" | "standby";
    mockTaskPoses.task_poses[name] = mockTaskPoses.task_poses[name] ?? {
      pose: [0, 0, 0, 0, 0, 0],
    };
    return ok(mockTaskPoses, `Mock task pose '${name}' recorded.`) as ApiEnvelope<T>;
  }
  if (path === "/api/drop-poses/record" && method === "POST") {
    const name = body?.name as "bottle" | "cup";
    mockDropPoses.drop_poses[name] = mockDropPoses.drop_poses[name] ?? {
      xy: [0, 0],
    };
    return ok(mockDropPoses, `Mock drop pose '${name}' recorded.`) as ApiEnvelope<T>;
  }
  if (path === "/api/follow/start" && method === "POST") {
    mockStatus = { ...mockStatus, busy: true, current_mode: "following", current_step: "target_hover" };
    return ok({ started: true } as T, "Mock follow started.");
  }
  if (path === "/api/follow/stop" && method === "POST") {
    mockStatus = { ...mockStatus, busy: false, current_mode: "idle", current_step: null };
    return ok({ stopped: true } as T, "Mock follow stopped.");
  }
  if (path === "/api/workflow/fake-grasp" && method === "POST") {
    mockStatus = { ...mockStatus, busy: true, current_mode: "running_fake_cycle", current_step: "home" };
    return ok({ started: true } as T, "Mock fake grasp started.");
  }
  if (path === "/api/workflow/stop" && method === "POST") {
    mockStatus = { ...mockStatus, busy: false, current_mode: "idle", current_step: null };
    return ok({ stopped: true } as T, "Mock workflow stopped.");
  }
  if (
    ["/api/robot/move-home", "/api/robot/move-work", "/api/robot/move-standby"].includes(path) &&
    method === "POST"
  ) {
    const step = path.replace("/api/robot/move-", "") as "home" | "work" | "standby";
    mockStatus = { ...mockStatus, busy: false, current_mode: "idle", current_step: step };
    return ok({ moved: step } as T, `Mock moved to ${step}.`);
  }

  return {
    ok: false,
    code: "UNKNOWN_ERROR",
    message: `Mock endpoint not implemented: ${method} ${path}`,
  };
}
