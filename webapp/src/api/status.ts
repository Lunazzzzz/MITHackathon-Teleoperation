import { apiRequest } from "./client";
import type { SystemStatus } from "../types/domain";

export function getStatus() {
  return apiRequest<SystemStatus>("/api/status");
}
