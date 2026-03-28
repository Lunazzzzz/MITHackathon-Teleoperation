import { useEffect, useState } from "react";
import { getStatus } from "../api/status";
import type { SystemStatus } from "../types/domain";

export function useStatusPolling(intervalMs = 500) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      const response = await getStatus();
      if (cancelled) {
        return;
      }
      if (response.ok && response.data) {
        setStatus(response.data);
        setError(null);
      } else {
        setError(response.message ?? "Failed to load status.");
      }
    };

    void tick();
    const timer = window.setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return { status, error, setStatus };
}
