import { apiRequest } from "./client";
import type { RuntimeConfig } from "../types/domain";

export function getRuntimeConfig() {
  return apiRequest<RuntimeConfig>("/api/runtime-config");
}

export function updateRuntimeConfig(config: RuntimeConfig) {
  return apiRequest<RuntimeConfig>("/api/config/runtime", {
    method: "POST",
    body: JSON.stringify(config),
  });
}
