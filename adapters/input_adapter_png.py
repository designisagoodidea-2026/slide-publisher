"""
input_adapter_png.py — accept PNG screenshot(s) as a deck source.

For v0.1, PNG inputs are treated as visual references for the visual-diff
loop (not as fully-classified inputs). OCR via tesseract is optional; if
unavailable, the adapter emits a minimal record with the image path so
downstream visual comparison still works.

Dependencies (optional):
    - pytesseract + Tesseract binary: text extraction.
      pip install pytesseract; brew install tesseract.
    - Pillow: image inspection (very commonly already installed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


def extract_one(png_path: Path, run_ocr: bool) -> dict[str, Any]:
    if not HAS_PIL:
        raise RuntimeError("Pillow required. pip install pillow")
    img = Image.open(png_path)
    width, height = img.size

    shapes: list[dict[str, Any]] = []
    if run_ocr and HAS_TESSERACT:
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            for i, txt in enumerate(data.get("text", [])):
                if not txt or not txt.strip():
                    continue
                shapes.append({
                    "kind": "text",
                    "x": int(data["left"][i]),
                    "y": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "text": txt,
                    "font_family": "",
                    "font_size_pt": int(data["height"][i] * 0.75),
                    "font_weight": 400,
                    "fill_hex": "",
                })
        except Exception:
            pass

    return {
        "slide_id": f"png:{png_path.name}",
        "shapes": shapes,
        "png_path": str(png_path),
        "image_size": {"width": width, "height": height},
    }


def extract(srcs: list[str], run_ocr: bool) -> dict[str, Any]:
    paths = [Path(s).expanduser() for s in srcs]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"PNG(s) not found: {missing}")
    slides = [extract_one(p, run_ocr) for p in paths]
    return {
        "source": [str(p) for p in paths],
        "source_kind": "png",
        "slides": slides,
        "page_pngs": [str(p) for p in paths],
        "existing_styles": {"colors": [], "text": []},
        "_capabilities": {
            "Pillow": HAS_PIL,
            "tesseract": HAS_TESSERACT,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Accept one or more PNG screenshots as deck source.")
    parser.add_argument("srcs", nargs="+", help="One or more PNG paths")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    parser.add_argument("--ocr", action="store_true", help="Run OCR via tesseract")
    args = parser.parse_args()

    try:
        result = extract(args.srcs, args.ocr)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    out_text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).expanduser().write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
