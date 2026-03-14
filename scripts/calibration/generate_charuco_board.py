#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from _common import build_charuco_board


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a printable OpenCV-native ChArUco board.")
    parser.add_argument("--board-cols", type=int, required=True, help="ChArUco square count along width")
    parser.add_argument("--board-rows", type=int, required=True, help="ChArUco square count along height")
    parser.add_argument("--square-size-mm", type=float, required=True, help="Checker square size in millimeters")
    parser.add_argument("--marker-size-mm", type=float, required=True, help="Marker size in millimeters")
    parser.add_argument("--aruco-dict", required=True, help="OpenCV dictionary name, e.g. DICT_4X4_50")
    parser.add_argument("--page-width-mm", type=float, default=297.0, help="Page width in millimeters")
    parser.add_argument("--page-height-mm", type=float, default=210.0, help="Page height in millimeters")
    parser.add_argument("--dpi", type=int, default=300, help="Output DPI for printable PNG/PDF")
    parser.add_argument("--output-prefix", required=True, help="Output path without extension")
    return parser.parse_args()


def mm_to_px(mm: float, dpi: int) -> int:
    return int(round(mm * dpi / 25.4))


def main() -> int:
    args = parse_args()
    if args.marker_size_mm >= args.square_size_mm:
        raise SystemExit("--marker-size-mm must be smaller than --square-size-mm")

    board_width_mm = args.board_cols * args.square_size_mm
    board_height_mm = args.board_rows * args.square_size_mm
    if board_width_mm > args.page_width_mm or board_height_mm > args.page_height_mm:
        raise SystemExit("Board does not fit inside the requested page size")

    board = build_charuco_board(
        args.board_cols,
        args.board_rows,
        args.square_size_mm,
        args.marker_size_mm,
        args.aruco_dict,
    )

    dpi = int(args.dpi)
    page_w_px = mm_to_px(args.page_width_mm, dpi)
    page_h_px = mm_to_px(args.page_height_mm, dpi)
    board_w_px = mm_to_px(board_width_mm, dpi)
    board_h_px = mm_to_px(board_height_mm, dpi)

    board_img = board.generateImage((board_w_px, board_h_px), marginSize=0, borderBits=1)
    page = np.full((page_h_px, page_w_px), 255, dtype=np.uint8)
    offset_x = (page_w_px - board_w_px) // 2
    offset_y = (page_h_px - board_h_px) // 2
    page[offset_y : offset_y + board_h_px, offset_x : offset_x + board_w_px] = board_img

    output_prefix = Path(args.output_prefix).expanduser().resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = output_prefix.with_suffix(".png")
    pdf_path = output_prefix.with_suffix(".pdf")
    json_path = output_prefix.with_suffix(".json")

    page_image = Image.fromarray(page)
    page_image.save(png_path, dpi=(dpi, dpi))
    page_image.save(pdf_path, resolution=dpi)

    metadata = {
        "board_type": "charuco",
        "board_cols": args.board_cols,
        "board_rows": args.board_rows,
        "square_size_mm": args.square_size_mm,
        "marker_size_mm": args.marker_size_mm,
        "aruco_dict": args.aruco_dict,
        "page_width_mm": args.page_width_mm,
        "page_height_mm": args.page_height_mm,
        "dpi": dpi,
        "board_width_mm": board_width_mm,
        "board_height_mm": board_height_mm,
        "board_width_px": board_w_px,
        "board_height_px": board_h_px,
        "page_width_px": page_w_px,
        "page_height_px": page_h_px,
        "board_offset_px": [offset_x, offset_y],
        "print_note": "Print at 100% scale with no fit-to-page scaling.",
    }
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Saved {png_path}")
    print(f"Saved {pdf_path}")
    print(f"Saved {json_path}")
    print(
        "Board area: "
        f"{board_width_mm:.1f} x {board_height_mm:.1f} mm, "
        f"centered on {args.page_width_mm:.1f} x {args.page_height_mm:.1f} mm page"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
