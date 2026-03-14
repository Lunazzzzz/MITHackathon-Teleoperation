from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from omnihand_2025_controller import OmniHandController


def load_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"YAML root must be a mapping: {config_path}")
    return data


def load_hand_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    data = load_yaml(config_path)
    hand_cfg = data.get("hand") if "hand" in data else data
    if not isinstance(hand_cfg, dict):
        raise SystemExit(f"Expected a hand config mapping in: {config_path}")
    cfg = dict(hand_cfg)
    cfg["enabled"] = True
    return cfg


class OmniHandActions:
    def __init__(self, config: str | Path | dict[str, Any], execute: bool = True) -> None:
        if isinstance(config, dict):
            hand_cfg = dict(config)
            hand_cfg["enabled"] = True
            self.config_path = None
        else:
            self.config_path = Path(config).expanduser().resolve()
            hand_cfg = load_hand_config(self.config_path)
        self.controller = OmniHandController(hand_cfg, execute=execute)

    def open_hand(self) -> None:
        self.controller.open()

    def close_hand(self) -> None:
        self.controller.close()

    def cycle_hand(self, pause_seconds: float = 1.0) -> None:
        self.open_hand()
        if pause_seconds > 0:
            time.sleep(pause_seconds)
        self.close_hand()
        if pause_seconds > 0:
            time.sleep(pause_seconds)
        self.open_hand()


def create_actions(config: str | Path | dict[str, Any], execute: bool = True) -> OmniHandActions:
    return OmniHandActions(config=config, execute=execute)


def open_hand(config: str | Path | dict[str, Any], execute: bool = True) -> None:
    create_actions(config=config, execute=execute).open_hand()


def close_hand(config: str | Path | dict[str, Any], execute: bool = True) -> None:
    create_actions(config=config, execute=execute).close_hand()
