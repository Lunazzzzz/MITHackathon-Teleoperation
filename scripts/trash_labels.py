from __future__ import annotations

from typing import Iterable

UNIFIED_TARGET_LABELS = [
    "bottle",
    "cup",
    "drink_can",
    "paper",
    "cardboard",
    "plastic_bag",
    "food_waste",
    "other_trash",
]

UNIFIED_TARGET_NAME_TO_ID = {name: idx for idx, name in enumerate(UNIFIED_TARGET_LABELS)}

DEFAULT_ACTIVE_TARGET_LABELS = ["bottle", "cup", "drink_can"]

_DIRECT_TARGET_MAP = {
    "bottle": "bottle",
    "plastic bottle": "bottle",
    "glass bottle": "bottle",
    "bottle plastic": "bottle",
    "bottle glass": "bottle",
    "pet bottle": "bottle",
    "water bottle": "bottle",
    "soda bottle": "bottle",
    "beer bottle": "bottle",
    "wine bottle": "bottle",
    "gym bottle": "bottle",
    "cup": "cup",
    "plastic cup": "cup",
    "paper cup": "cup",
    "disposable cup": "cup",
    "cup disposable": "cup",
    "cup handle": "cup",
    "mug": "cup",
    "glass mug": "cup",
    "glass cup": "cup",
    "drink can": "drink_can",
    "tin can": "drink_can",
    "soda can": "drink_can",
    "beer can": "drink_can",
    "metal can": "drink_can",
    "aluminum can": "drink_can",
    "aluminium can": "drink_can",
    "can": "drink_can",
    "paper": "paper",
    "newspaper": "paper",
    "magazine": "paper",
    "receipt": "paper",
    "flyer": "paper",
    "document": "paper",
    "sheet paper": "paper",
    "cardboard": "cardboard",
    "paperboard": "cardboard",
    "carton": "cardboard",
    "cardboard box": "cardboard",
    "shipping box": "cardboard",
    "pizza box": "cardboard",
    "box": "cardboard",
    "plastic bag": "plastic_bag",
    "shopping bag": "plastic_bag",
    "garbage bag": "plastic_bag",
    "trash bag": "plastic_bag",
    "food waste": "food_waste",
    "leftover": "food_waste",
    "leftovers": "food_waste",
    "banana peel": "food_waste",
    "orange peel": "food_waste",
    "apple core": "food_waste",
    "fruit peel": "food_waste",
    "vegetable scrap": "food_waste",
    "other trash": "other_trash",
    "trash": "other_trash",
    "garbage": "other_trash",
    "rubbish": "other_trash",
    "wrapper": "other_trash",
    "packaging": "other_trash",
    "package": "other_trash",
    "foam": "other_trash",
    "styrofoam": "other_trash",
    "cigarette": "other_trash",
    "mask": "other_trash",
    # Preserve the legacy runtime workaround for a frequent bottle misclassification.
    "cell phone": "bottle",
}

_OTHER_TRASH_KEYWORDS = {
    "trash",
    "garbage",
    "rubbish",
    "wrapper",
    "packaging",
    "package",
    "foam",
    "styrofoam",
    "cigarette",
    "mask",
}

_FOOD_WASTE_KEYWORDS = {
    "food",
    "peel",
    "leftover",
    "banana",
    "orange",
    "apple core",
    "fruit",
    "vegetable",
    "bone",
}


def normalize_label_text(name: str) -> str:
    text = str(name).strip().lower().replace("-", " ").replace("_", " ")
    return " ".join(text.split())


def canonicalize_target_label(name: str) -> str | None:
    text = normalize_label_text(name)
    if text in _DIRECT_TARGET_MAP:
        return _DIRECT_TARGET_MAP[text]
    if text in UNIFIED_TARGET_LABELS:
        return text
    return None


def resolve_target_name(name: str) -> str | None:
    text = normalize_label_text(name)
    direct = canonicalize_target_label(text)
    if direct is not None:
        return direct
    if "bottle" in text and "cap" not in text and "lid" not in text:
        return "bottle"
    if any(token in text for token in ("cup", "mug", "tumbler")):
        return "cup"
    if "can" in text and all(token not in text for token in ("cap", "lid", "trash can", "garbage can", "watering can", "canister")):
        return "drink_can"
    if "cardboard" in text or "paperboard" in text or "carton" in text:
        return "cardboard"
    if "paper" in text:
        return "paper"
    if "bag" in text and any(token in text for token in ("plastic", "shopping", "garbage", "trash")):
        return "plastic_bag"
    if any(token in text for token in _FOOD_WASTE_KEYWORDS):
        return "food_waste"
    if any(token in text for token in _OTHER_TRASH_KEYWORDS):
        return "other_trash"
    return None


def normalize_requested_target_labels(
    labels: Iterable[str] | None,
    *,
    default: Iterable[str] | None = None,
) -> list[str]:
    source = list(labels or default or [])
    normalized: list[str] = []
    seen: set[str] = set()
    for label in source:
        canonical = canonicalize_target_label(label)
        if canonical is None:
            raise ValueError(
                f"Unsupported target label: {label}. Expected one of: {', '.join(UNIFIED_TARGET_LABELS)}"
            )
        if canonical in seen:
            continue
        normalized.append(canonical)
        seen.add(canonical)
    return normalized

