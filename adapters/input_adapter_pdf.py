"""
input_adapter_pdf.py — accept a PDF (URL or local path) as a deck source.

Extracts per-page text + positions and renders each page to PNG. Output is
a normalized JSON describing the deck in the same shape the Figma MCP walk
produces — slides with shapes, so downstream classifier / synthesizer /
visual-diff can treat PDF as just another input format.

Dependencies (optional, gracefully degraded):
    - pdfplumber: text + position extraction. pip install pdfplumber
    - pdf2image:  page-to-PNG rendering. Requires poppler binary.
                  pip install pdf2image. On macOS: brew install poppler.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlretrieve

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False


def _classify_text_size(size_pt: float) -> str:
    """Coarse kind based on font size — same heuristic the synthesizers use."""
    if size_pt >= 40:
        return "title"
    if size_pt >= 20:
        return "heading"
    if size_pt >= 12:
        return "body"
    return "caption"


def _resolve_source(src: str, tmp_dir: Path) -> Path:
    """If src is a URL, download to a temp file. Otherwise treat as path."""
    parsed = urlparse(src)
    if parsed.scheme in {"http", "https"}:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        target = tmp_dir / (Path(parsed.path).name or "downloaded.pdf")
        urlretrieve(src, str(target))
        return target
    return Path(src).expanduser()


def extract(src: str, render_pngs: bool, tmp_dir: Path) -> dict[str, Any]:
    if not HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber is required for PDF input. "
                            "Install: pip install pdfplumber")
    path = _resolve_source(src, tmp_dir)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    slides: list[dict[str, Any]] = []
    png_paths: list[str] = []

    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            shapes: list[dict[str, Any]] = []
            for ch in page.chars or []:
                # pdfplumber's `chars` gives per-character positions; group
                # into runs by adjacent positions + same font for shape-level
                # output. For v0.1 simplicity, emit one shape per non-empty
                # text-run grouping by line.
                pass  # simpler: use page.extract_words for grouping

            for word in page.extract_words(use_text_flow=True) or []:
                font_size = float(word.get("size", 12))
                shapes.append({
                    "kind": "text",
                    "x": float(word.get("x0", 0)),
                    "y": float(word.get("top", 0)),
                    "width": float(word.get("x1", 0) - word.get("x0", 0)),
                    "height": float(word.get("bottom", 0) - word.get("top", 0)),
                    "text": word.get("text", ""),
                    "font_family": word.get("fontname", "").split("+")[-1],
                    "font_size_pt": font_size,
                    "font_weight": 700 if "bold" in str(word.get("fontname", "")).lower() else 400,
                    "fill_hex": "",
                    "text_kind": _classify_text_size(font_size),
                })

            slides.append({
                "slide_id": f"pdf:page:{i+1}",
                "shapes": shapes,
            })

    if render_pngs and HAS_PDF2IMAGE:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        images = convert_from_path(str(path), dpi=120)
        for i, img in enumerate(images):
            out = tmp_dir / f"page-{i+1:03d}.png"
            img.save(str(out), "PNG")
            png_paths.append(str(out))
            if i < len(slides):
                slides[i]["png_path"] = str(out)

    return {
        "source": str(path),
        "source_kind": "pdf",
        "slides": slides,
        "page_pngs": png_paths,
        "existing_styles": {"colors": [], "text": []},
        "_capabilities": {
            "pdfplumber": HAS_PDFPLUMBER,
            "pdf2image": HAS_PDF2IMAGE,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Accept a PDF (URL or path) as a deck source. Emits "
                    "normalized JSON.")
    parser.add_argument("src", help="PDF URL or local file path")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    parser.add_argument("--render-pngs", action="store_true",
                        help="Also render each page to PNG (requires pdf2image + poppler)")
    parser.add_argument("--tmp-dir", default="/tmp/slide-publisher-pdf-input",
                        help="Temporary directory for downloaded PDFs and PNGs")
    args = parser.parse_args()

    try:
        result = extract(args.src, args.render_pngs, Path(args.tmp_dir))
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
