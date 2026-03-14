import { useState } from "react";
import type { ApiEnvelope } from "../types/api";

export function useApiAction() {
  const [pending, setPending] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  async function run<T>(action: () => Promise<ApiEnvelope<T>>) {
    setPending(true);
    setLastError(null);
    try {
      const response = await action();
      if (!response.ok) {
        setLastError(response.message ?? "Action failed.");
      }
      return response;
    } finally {
      setPending(false);
    }
  }

  return { pending, lastError, run };
}
