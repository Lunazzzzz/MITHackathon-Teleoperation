from __future__ import annotations

import time
from typing import Any, Iterable, Sequence


def _parse_angles(cfg: dict[str, Any], key: str) -> list[float] | None:
    raw = cfg.get(key)
    if raw is None:
        return None
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        raise SystemExit(f"OmniHand config '{key}' must be a list of 10 floats.")
    values = [float(v) for v in raw]
    if len(values) != 10:
        raise SystemExit(f"OmniHand config '{key}' must have 10 joint angles, got {len(values)}.")
    return values


def _resolve_hand_type(value: Any) -> int:
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise SystemExit(f"OmniHand hand_type must be 0 (left) or 1 (right), got {value}.")
    if value is None:
        return 0
    text = str(value).strip().lower()
    if text in ("0", "left", "l"):
        return 0
    if text in ("1", "right", "r"):
        return 1
    raise SystemExit(f"OmniHand hand_type must be left/right or 0/1, got '{value}'.")


def _resolve_transport(value: Any) -> str:
    if value is None:
        return "can"
    text = str(value).strip().lower()
    if text in ("can", "canfd", "zlg"):
        return "can"
    if text in ("serial", "uart", "rs485", "rs-485"):
        return "serial"
    raise SystemExit(f"OmniHand transport must be can or serial, got '{value}'.")


class OmniHandController:
    def __init__(self, cfg: dict[str, Any], execute: bool) -> None:
        self.enabled = bool(cfg.get("enabled", False))
        self.execute = bool(execute and self.enabled)
        self.transport = _resolve_transport(cfg.get("transport", "can"))
        self.device_id = int(cfg.get("device_id", 1))
        self.canfd_id = int(cfg.get("canfd_id", 0))
        self.serial_port = str(cfg.get("serial_port", "/dev/ttyUSB0"))
        self.serial_baudrate = int(cfg.get("serial_baudrate", 460800))
        self.hand_type = _resolve_hand_type(cfg.get("hand_type", "left"))
        self.open_angles = _parse_angles(cfg, "open_angles_rad")
        self.close_angles = _parse_angles(cfg, "close_angles_rad")
        self.open_wait_s = float(cfg.get("open_wait_s", 0.4))
        self.close_wait_s = float(cfg.get("close_wait_s", 0.5))
        self.show_data_details = bool(cfg.get("show_data_details", False))
        self.hand = None

        if self.execute:
            if self.open_angles is None or self.close_angles is None:
                raise SystemExit(
                    "OmniHand enabled but open/close angles are missing. "
                    "Set hand.open_angles_rad and hand.close_angles_rad in the config."
                )
            self._connect()

    def _connect(self) -> None:
        try:
            from omnihand_2025 import AgibotHandO10
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "OmniHand SDK Python package is not installed. "
                "Install the vendor wheel (agibot_hand_py-*.whl) or build from "
                "third_party/Omnihand-2025-SDK/python before running with --go."
            ) from exc
        self.hand = AgibotHandO10.create_hand(
            device_id=self.device_id,
            canfd_id=self.canfd_id,
            hand_type=self.hand_type,
            transport=self.transport,
            uart_port=self.serial_port,
            uart_baudrate=self.serial_baudrate,
        )
        if self.show_data_details:
            self.hand.show_data_details(True)

    def _apply_angles(self, angles: Sequence[float], wait_s: float) -> None:
        if not self.hand:
            return
        self.hand.set_all_active_joint_angles(list(angles))
        if wait_s > 0:
            time.sleep(wait_s)

    def open(self) -> None:
        if not self.execute:
            return
        if self.open_angles is None:
            raise SystemExit("OmniHand open requested but open_angles_rad is not configured.")
        self._apply_angles(self.open_angles, self.open_wait_s)

    def close(self) -> None:
        if not self.execute:
            return
        if self.close_angles is None:
            raise SystemExit("OmniHand close requested but close_angles_rad is not configured.")
        self._apply_angles(self.close_angles, self.close_wait_s)


def build_omnihand_controller(cfg: dict[str, Any], execute: bool) -> OmniHandController | None:
    if not isinstance(cfg, dict):
        return None
    if not bool(cfg.get("enabled", False)):
        return None
    controller = OmniHandController(cfg, execute=execute)
    return controller
