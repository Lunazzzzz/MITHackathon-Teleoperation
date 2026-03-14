from __future__ import annotations

import sys
from pathlib import Path


def prefer_local_pyagxarm(current_file: str) -> Path | None:
    current_path = Path(current_file).resolve()
    for parent in current_path.parents:
        sdk_root = parent / "pyAgxArm"
        package_init = sdk_root / "pyAgxArm" / "__init__.py"
        if not package_init.exists():
            continue
        sdk_root_str = str(sdk_root)
        if sdk_root_str not in sys.path:
            sys.path.insert(0, sdk_root_str)
        return sdk_root
    return None
