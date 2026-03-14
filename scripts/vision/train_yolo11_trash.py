#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a YOLO11 trash detector for bottle/cup classification.")
    parser.add_argument("--dataset", required=True, help="Ultralytics dataset YAML path")
    parser.add_argument("--model", default="yolo11s.pt", help="Starting model weights")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0", help="CUDA device id, e.g. 0")
    parser.add_argument("--project", default="runs/detect", help="Training project directory")
    parser.add_argument("--name", default="trash_yolo11s", help="Training run name")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--cache", default="ram", choices=["ram", "disk", "False", "false"], help="Ultralytics cache mode")
    parser.add_argument("--close-mosaic", type=int, default=10, help="Disable mosaic in the last N epochs")
    return parser.parse_args()


def require_cuda(device: str) -> None:
    if str(device) in {"cpu", "mps"}:
        raise SystemExit("GPU is required for training; do not use CPU or MPS")
    if not torch.cuda.is_available():
        raise SystemExit("torch.cuda.is_available() is False; GPU setup is incomplete")


def normalize_cache(value: str) -> str | bool:
    if value.lower() == "false":
        return False
    return value


def main() -> int:
    args = parse_args()
    require_cuda(args.device)
    dataset = Path(args.dataset).expanduser().resolve()
    if not dataset.exists():
        raise SystemExit(f"Dataset YAML does not exist: {dataset}")

    model = YOLO(args.model)
    results = model.train(
        data=str(dataset),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        workers=args.workers,
        patience=args.patience,
        cache=normalize_cache(args.cache),
        close_mosaic=args.close_mosaic,
        pretrained=True,
    )
    print(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
