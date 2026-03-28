import { apiRequest } from "./client";
import type { DetectionState } from "../types/domain";

export function getDetectionState() {
  return apiRequest<DetectionState>("/api/detection/state");
}
