from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root(current_file: str) -> Path:
    current_path = Path(current_file).resolve()
    for parent in [current_path.parent, *current_path.parents]:
        if (parent / "scripts").exists() and (parent / "third_party").exists():
            return parent
    return current_path.parents[1]


def prefer_repo_root(current_file: str) -> Path:
    root = _repo_root(current_file)
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def is_binaryattention_reference(ref: str | os.PathLike[str] | None) -> bool:
    if ref is None:
        return False
    text = str(ref).strip().lower()
    return "binaryattn" in text or "binaryattention" in text


def maybe_enable_binaryattention(current_file: str, *refs: str | os.PathLike[str] | None, verbose: bool = False) -> bool:
    env_flag = os.environ.get("SORT_TRASH_BINARYATTN", "").strip().lower()
    enabled = env_flag in {"1", "true", "yes", "on"} or any(is_binaryattention_reference(ref) for ref in refs)
    if not enabled:
        return False

    prefer_repo_root(current_file)
    from third_party.ultralytics_binaryattn import register_binaryattention

    register_binaryattention(verbose=verbose)
    return True
