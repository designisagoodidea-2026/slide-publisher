"""
input_adapter_ppt.py — accept legacy .ppt format by converting to .pptx
via LibreOffice headless.

LibreOffice is required (external binary dependency). Install on macOS:
    brew install --cask libreoffice
On Linux:
    apt-get install libreoffice

After conversion, the .pptx flows through the existing pptx pipeline.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def find_libreoffice() -> str | None:
    """Find a LibreOffice binary on the system."""
    for candidate in ("libreoffice", "soffice"):
        path = shutil.which(candidate)
        if path:
            return path
    macos_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if Path(macos_path).exists():
        return macos_path
    return None


def convert(ppt_path: Path, out_dir: Path) -> Path:
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install:\n"
            "  macOS:   brew install --cask libreoffice\n"
            "  Linux:   apt-get install libreoffice"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pptx",
         "--outdir", str(out_dir), str(ppt_path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice failed: {result.stderr}")
    out_path = out_dir / (ppt_path.stem + ".pptx")
    if not out_path.exists():
        raise RuntimeError(f"Conversion succeeded but {out_path} not found.")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a legacy .ppt file to .pptx via LibreOffice headless.")
    parser.add_argument("ppt", help="Path to .ppt")
    parser.add_argument("--out-dir", default="/tmp/slide-publisher-ppt-input",
                        help="Output directory for converted .pptx")
    args = parser.parse_args()

    ppt_path = Path(args.ppt).expanduser()
    if not ppt_path.exists():
        print(f"ERROR: {ppt_path} not found.", file=sys.stderr)
        return 2

    try:
        out = convert(ppt_path, Path(args.out_dir))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    result = {
        "source": str(ppt_path),
        "source_kind": "ppt",
        "converted_pptx": str(out),
        "note": (
            "Continue with template-classifier --format pptx on the "
            "converted .pptx for downstream pipeline."
        ),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
