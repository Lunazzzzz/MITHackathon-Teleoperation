#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _local_sdk import prefer_local_pyagxarm

prefer_local_pyagxarm(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-check the local sort_trash development environment.")
    parser.add_argument("--config", default="", help="Optional pipeline config to validate")
    parser.add_argument("--try-camera", action="store_true", help="Attempt to enumerate RealSense devices")
    parser.add_argument("--try-model", action="store_true", help="Attempt to load the configured YOLO model")
    return parser.parse_args()


def status_line(name: str, ok: bool, detail: str) -> str:
    prefix = "OK" if ok else "FAIL"
    return f"[{prefix}] {name}: {detail}"


def check_python() -> tuple[bool, str]:
    version = sys.version.split()[0]
    ok = sys.version_info[:2] == (3, 10)
    return ok, f"python={version}"


def check_import(module_name: str) -> tuple[bool, str]:
    try:
        module = __import__(module_name)
    except Exception as exc:
        return False, str(exc)
    version = getattr(module, "__version__", "imported")
    return True, f"version={version}"


def check_torch() -> tuple[bool, str]:
    try:
        import torch
    except Exception as exc:
        return False, str(exc)
    return True, f"torch={torch.__version__}, cuda_available={torch.cuda.is_available()}"


def check_pyagxarm() -> tuple[bool, str]:
    try:
        import pyAgxArm
    except Exception as exc:
        return False, str(exc)
    locations = list(pyAgxArm.__path__)
    repo_path = str(ROOT_DIR / "pyAgxArm" / "pyAgxArm")
    ok = repo_path in locations
    return ok, f"paths={locations}"


def validate_config(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing file: {path}"
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        return False, "config root is not a mapping"
    required_keys = {"model", "calibration_file", "camera", "workflow", "robot", "classes"}
    missing = sorted(required_keys - set(config))
    if missing:
        return False, f"missing keys: {missing}"
    return True, f"keys={sorted(config.keys())}"


def try_camera_enum() -> tuple[bool, str]:
    try:
        import pyrealsense2 as rs
        ctx = rs.context()
        devs = ctx.query_devices()
        devices = []
        for dev in devs:
            try:
                devices.append(
                    f"{dev.get_info(rs.camera_info.name)}:{dev.get_info(rs.camera_info.serial_number)}"
                )
            except Exception:
                devices.append("device-present")
        return True, f"devices={devices}"
    except Exception as exc:
        return False, str(exc)


def try_model_load(config_path: Path) -> tuple[bool, str]:
    try:
        from ultralytics import YOLO
    except Exception as exc:
        return False, str(exc)

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    model_path = Path(config["model"])
    if not model_path.is_absolute():
        model_path = (ROOT_DIR / model_path).resolve()
    if not model_path.exists():
        return False, f"missing model: {model_path}"
    try:
        YOLO(str(model_path))
    except Exception as exc:
        return False, str(exc)
    return True, f"loaded={model_path}"


def main() -> int:
    args = parse_args()
    checks: list[tuple[str, bool, str]] = []
    for name, fn in [
        ("python", check_python),
        ("numpy", lambda: check_import("numpy")),
        ("scipy", lambda: check_import("scipy")),
        ("yaml", lambda: check_import("yaml")),
        ("cv2", lambda: check_import("cv2")),
        ("pyrealsense2", lambda: check_import("pyrealsense2")),
        ("ultralytics", lambda: check_import("ultralytics")),
        ("torch", check_torch),
        ("pyAgxArm", check_pyagxarm),
    ]:
        ok, detail = fn()
        checks.append((name, ok, detail))

    config_path = None
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        ok, detail = validate_config(config_path)
        checks.append(("config", ok, detail))
    if args.try_camera:
        ok, detail = try_camera_enum()
        checks.append(("camera-enum", ok, detail))
    if args.try_model:
        if config_path is None:
            checks.append(("model-load", False, "--config is required with --try-model"))
        else:
            ok, detail = try_model_load(config_path)
            checks.append(("model-load", ok, detail))

    for name, ok, detail in checks:
        print(status_line(name, ok, detail))

    failures = [name for name, ok, _ in checks if not ok]
    if failures:
        print(f"Summary: failures={failures}")
        return 1
    print("Summary: all checks passed")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT_DIR)
    raise SystemExit(main())
