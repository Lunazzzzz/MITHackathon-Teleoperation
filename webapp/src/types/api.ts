export type ApiErrorCode =
  | "CAN_DOWN"
  | "BUSY"
  | "MIN_Z_BLOCKED"
  | "MISSING_TASK_POSE"
  | "MISSING_DROP_POSE"
  | "CAMERA_NOT_READY"
  | "MODEL_NOT_READY"
  | "UNKNOWN_ERROR";

export interface ApiEnvelope<T> {
  ok: boolean;
  message?: string;
  code?: ApiErrorCode | string;
  data?: T;
}
