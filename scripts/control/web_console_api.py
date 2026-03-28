#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from _web_console_motion import WebConsoleError
from _web_console_runtime import (
    DEFAULT_DROP_POSES_PATH,
    DEFAULT_HAND_CONFIG_PATH,
    DEFAULT_RUNTIME_CONFIG_PATH,
    DEFAULT_TASK_POSES_PATH,
    WebConsoleRuntime,
)
from _common import default_model_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FastAPI bridge for the sort_trash web console.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=str(default_model_path()))
    parser.add_argument("--device", default="0")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--camera-serial", default="")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--rotate-inference",
        choices=["none", "cw90", "ccw90", "180"],
        default="none",
    )
    parser.add_argument(
        "--rotate-inference-modes",
        nargs="*",
        choices=["none", "cw90", "ccw90", "180"],
        default=["none", "cw90", "ccw90"],
    )
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--depth-window", type=int, default=2)
    parser.add_argument("--calibration-file", required=True)
    parser.add_argument("--task-poses-file", default=str(DEFAULT_TASK_POSES_PATH))
    parser.add_argument("--drop-poses-file", default=str(DEFAULT_DROP_POSES_PATH))
    parser.add_argument("--hand-config", default=str(DEFAULT_HAND_CONFIG_PATH))
    parser.add_argument("--runtime-config-file", default=str(DEFAULT_RUNTIME_CONFIG_PATH))
    parser.add_argument("--channel", default="can0")
    parser.add_argument("--robot", default="nero")
    parser.add_argument("--speed-percent", type=int, default=10)
    parser.add_argument("--send-order", default="mode_target_mode", choices=["sdk", "target_then_mode", "mode_then_target", "mode_target_mode"])
    parser.add_argument("--mode-resend", type=int, default=3)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    return parser.parse_args()


class RecordPoseRequest(BaseModel):
    name: str
    overwrite: bool = False


class RuntimeConfigRequest(BaseModel):
    hover_height_m: float
    grasp_z_offset_m: float
    drop_hover_z_m: float
    drop_z_m: float
    follow_rate_hz: float
    imgsz: int
    base_offset_m: list[float]
    pose_rpy_deg: list[float]
    rotate_inference_modes: list[str]
    target_labels: list[str]


def ok(data: Any, message: str | None = None) -> JSONResponse:
    payload = {"ok": True, "data": data}
    if message:
        payload["message"] = message
    return JSONResponse(payload)


def fail(message: str, code: str = "UNKNOWN_ERROR") -> JSONResponse:
    return JSONResponse({"ok": False, "message": message, "code": code})


def create_app(runtime: WebConsoleRuntime) -> FastAPI:
    app = FastAPI(title="sort_trash web console", version="0.1.0")

    @app.on_event("startup")
    async def _startup() -> None:
        runtime.startup()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        runtime.shutdown()

    @app.get("/api/status")
    async def get_status():
        return ok(runtime.get_status())

    @app.get("/api/detection/state")
    async def get_detection_state():
        return ok(runtime.get_detection_state())

    @app.get("/api/video.mjpg")
    async def get_video():
        return StreamingResponse(
            runtime.mjpeg_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/api/task-poses")
    async def get_task_poses():
        return ok(runtime.get_task_poses())

    @app.get("/api/drop-poses")
    async def get_drop_poses():
        return ok(runtime.get_drop_poses())

    @app.get("/api/runtime-config")
    async def get_runtime_config():
        return ok(runtime.get_runtime_config())

    @app.post("/api/task-poses/record")
    async def post_task_pose(body: RecordPoseRequest):
        try:
            return ok(runtime.record_task_pose(body.name, body.overwrite), f"Task pose '{body.name}' recorded.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/drop-poses/record")
    async def post_drop_pose(body: RecordPoseRequest):
        try:
            return ok(runtime.record_drop_pose(body.name, body.overwrite), f"Drop pose '{body.name}' recorded.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/config/runtime")
    async def post_runtime_config(body: RuntimeConfigRequest):
        try:
            return ok(runtime.update_runtime_config(body.model_dump()), "Runtime config updated.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/robot/move-home")
    async def move_home():
        try:
            runtime.move_named_pose("home")
            return ok({"moved": "home"}, "Moved to home.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/robot/move-work")
    async def move_work():
        try:
            runtime.move_named_pose("work")
            return ok({"moved": "work"}, "Moved to work.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/robot/move-standby")
    async def move_standby():
        try:
            runtime.move_named_pose("standby")
            return ok({"moved": "standby"}, "Moved to standby.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/workflow/fake-grasp")
    async def post_fake_grasp():
        try:
            runtime.start_fake_grasp()
            return ok({"started": True}, "Fake grasp started.")
        except WebConsoleError as exc:
            return fail(exc.message, exc.code)

    @app.post("/api/workflow/stop")
    async def post_stop():
        runtime.stop_workflow()
        return ok({"stopped": True}, "Stop requested.")

    @app.post("/api/follow/start")
    async def post_follow_start():
        return fail("Follow is not wired in v1.", "UNKNOWN_ERROR")

    @app.post("/api/follow/stop")
    async def post_follow_stop():
        return fail("Follow is not wired in v1.", "UNKNOWN_ERROR")

    return app


def main() -> int:
    args = parse_args()
    runtime = WebConsoleRuntime(args)
    app = create_app(runtime)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
