#!/usr/bin/env python3
from __future__ import annotations

MIN_TOOL_Z_M = 0.10


def check_pose_min_z(pose: list[float] | tuple[float, ...], label: str, *, min_z_m: float = MIN_TOOL_Z_M) -> bool:
    z_m = float(pose[2])
    if z_m >= min_z_m:
        return True
    print(
        f"[SAFETY] Refusing to execute {label}: target z={z_m:.3f} m is below the minimum "
        f"allowed z={min_z_m:.3f} m."
    )
    return False
