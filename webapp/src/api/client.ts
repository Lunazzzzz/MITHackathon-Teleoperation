import { mockRequest } from "../mocks/mockServer";
import type { ApiEnvelope } from "../types/api";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

async function realRequest<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  try {
    const response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const json = (await response.json()) as ApiEnvelope<T>;
    return json;
  } catch (error) {
    return {
      ok: false,
      code: "UNKNOWN_ERROR",
      message: error instanceof Error ? error.message : "Unknown network error",
    };
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  if (USE_MOCK) {
    return mockRequest<T>(path, init);
  }
  return realRequest<T>(path, init);
}

export function isMockMode() {
  return USE_MOCK;
}
