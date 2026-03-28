import { useEffect, useState } from "react";
import { getDetectionState } from "../api/detection";
import type { DetectionState } from "../types/domain";

export function useDetectionPolling(intervalMs = 500) {
  const [detection, setDetection] = useState<DetectionState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      const response = await getDetectionState();
      if (cancelled) {
        return;
      }
      if (response.ok && response.data) {
        setDetection(response.data);
        setError(null);
      } else {
        setError(response.message ?? "Failed to load detection state.");
      }
    };

    void tick();
    const timer = window.setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [intervalMs]);

  return { detection, error };
}
