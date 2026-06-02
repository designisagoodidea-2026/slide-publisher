"""
visual_diff.py — visual comparison of input deck vs rendered output.

Renders both sides to per-slide PNGs, computes per-slide perceptual hash +
SSIM-style similarity, and emits an HTML side-by-side diff artifact plus a
JSON summary.

Dependencies (optional, gracefully degraded):
    - Pillow: image I/O. pip install pillow
    - imagehash: perceptual hashing. pip install imagehash
    - scikit-image: SSIM similarity score. pip install scikit-image
    - pdf2image: render pptx (via LibreOffice → PDF → PNG) and PDF inputs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Any

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import imagehash
    HAS_HASH = True
except ImportError:
    HAS_HASH = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from skimage.metrics import structural_similarity as ssim
    HAS_SSIM = HAS_NUMPY
except ImportError:
    HAS_SSIM = False


def find_libreoffice() -> str | None:
    for c in ("libreoffice", "soffice"):
        p = shutil.which(c)
        if p:
            return p
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if Path(mac).exists():
        return mac
    return None


def render_pptx_to_pngs(pptx_path: Path, out_dir: Path) -> list[Path]:
    """Convert .pptx → PDF → per-page PNG via LibreOffice + pdf2image."""
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError("LibreOffice not found; needed to render pptx for diff.")
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError("pdf2image not installed. pip install pdf2image")
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        soffice, "--headless", "--convert-to", "pdf",
        "--outdir", str(out_dir), str(pptx_path),
    ], capture_output=True, text=True, check=True, timeout=120)
    pdf_path = out_dir / (pptx_path.stem + ".pdf")
    images = convert_from_path(str(pdf_path), dpi=120)
    paths = []
    for i, img in enumerate(images):
        p = out_dir / f"{pptx_path.stem}-slide-{i+1:03d}.png"
        img.save(str(p), "PNG")
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Region split — top/middle/bottom bands the anomaly classifier reasons about.
# Title and footer ratios are deliberately conservative (15 / 70 / 15) so that
# common cases — title bar at the top, decorative footer, body filling the
# middle — land in the right band. Tunable per template via profile.
# ---------------------------------------------------------------------------

REGIONS = [
    ("title",  0.00, 0.25),
    ("body",   0.20, 0.85),
    ("footer", 0.80, 1.00),
]


def _crop_region(img, target_w: int, target_h: int, y0: float, y1: float):
    """Crop the [y0..y1] vertical band from a target-sized image."""
    top = int(target_h * y0)
    bot = int(target_h * y1)
    return img.crop((0, top, target_w, bot))


def _region_metrics(a_img, b_img, region_name: str) -> dict[str, Any]:
    """Compute SSIM + pHash + mean-color delta on a single region pair."""
    out: dict[str, Any] = {"region": region_name}
    if HAS_HASH:
        ha = imagehash.phash(a_img)
        hb = imagehash.phash(b_img)
        bits = len(ha.hash) * len(ha.hash[0])
        out["phash_distance"] = ha - hb
        out["phash_similarity"] = round(1 - (ha - hb) / bits, 4)
    if HAS_SSIM:
        a_arr = np.array(a_img.convert("L"))
        b_arr = np.array(b_img.convert("L"))
        try:
            out["ssim"] = round(float(ssim(a_arr, b_arr)), 4)
        except Exception as e:
            out["ssim_error"] = str(e)
    # Mean-color delta — cheap proxy for "fill changed" / "color theme shift".
    if HAS_NUMPY:
        a_rgb = np.array(a_img.convert("RGB"))
        b_rgb = np.array(b_img.convert("RGB"))
        mean_a = a_rgb.reshape(-1, 3).mean(axis=0)
        mean_b = b_rgb.reshape(-1, 3).mean(axis=0)
        delta = mean_b - mean_a
        out["mean_color_delta"] = {
            "r": round(float(delta[0]), 2),
            "g": round(float(delta[1]), 2),
            "b": round(float(delta[2]), 2),
            "magnitude": round(float(np.linalg.norm(delta)), 2),
        }
        out["variance_a"] = round(float(a_rgb.var()), 2)
        out["variance_b"] = round(float(b_rgb.var()), 2)
    else:
        # Pure-PIL fallback: stat-based mean
        a_stat = a_img.getextrema()
        b_stat = b_img.getextrema()
        out["pil_extrema_a"] = a_stat
        out["pil_extrema_b"] = b_stat
    return out


def compare_pair(a_path: Path, b_path: Path) -> dict[str, Any]:
    """Return similarity metrics for one pair of slide PNGs.

    Output shape:
        {
          a, b,
          phash_similarity, ssim,              # whole-slide
          regions: [
            {region: 'title',  phash_similarity, ssim, mean_color_delta, ...},
            {region: 'body',   ...},
            {region: 'footer', ...},
          ],
        }
    """
    if not HAS_PIL:
        return {"error": "Pillow missing"}
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    target_w, target_h = 1280, 720
    a_r = a.resize((target_w, target_h))
    b_r = b.resize((target_w, target_h))

    out: dict[str, Any] = {"a": str(a_path), "b": str(b_path)}

    if HAS_HASH:
        ha = imagehash.phash(a_r)
        hb = imagehash.phash(b_r)
        bits = len(ha.hash) * len(ha.hash[0])
        out["phash_distance"] = ha - hb
        out["phash_similarity"] = round(1 - (ha - hb) / bits, 4)

    if HAS_SSIM:
        a_arr = np.array(a_r.convert("L"))
        b_arr = np.array(b_r.convert("L"))
        out["ssim"] = round(float(ssim(a_arr, b_arr)), 4)

    # Per-region — the anomaly classifier reads these.
    out["regions"] = []
    for name, y0, y1 in REGIONS:
        a_band = _crop_region(a_r, target_w, target_h, y0, y1)
        b_band = _crop_region(b_r, target_w, target_h, y0, y1)
        out["regions"].append(_region_metrics(a_band, b_band, name))

    return out


def diff(input_pngs: list[Path], output_pptx: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_pptx_to_pngs(output_pptx, out_dir / "rendered")
    n = min(len(input_pngs), len(rendered))
    pairs = []
    for i in range(n):
        pairs.append(compare_pair(input_pngs[i], rendered[i]))
    # Compute aggregate parity score (mean SSIM if available, else phash)
    metric_key = "ssim" if HAS_SSIM else "phash_similarity"
    metrics = [p.get(metric_key) for p in pairs if metric_key in p]
    aggregate = round(sum(metrics) / len(metrics), 4) if metrics else None

    html = _build_html(pairs, metric_key, aggregate)
    html_path = out_dir / "diff.html"
    html_path.write_text(html)

    return {
        "input_n": len(input_pngs),
        "output_n": len(rendered),
        "pairs_compared": n,
        "metric_key": metric_key,
        "aggregate_parity": aggregate,
        "per_pair": pairs,
        "html_report": str(html_path),
    }


def _build_html(pairs: list[dict[str, Any]], metric_key: str,
                aggregate: float | None) -> str:
    rows = []
    for i, p in enumerate(pairs, 1):
        a = Path(p.get("a", ""))
        b = Path(p.get("b", ""))
        m = p.get(metric_key, "n/a")
        rows.append(f"""
<tr>
  <td>{i}</td>
  <td><img src="{a.name}" style="max-width:400px"></td>
  <td><img src="{b.name}" style="max-width:400px"></td>
  <td>{m}</td>
</tr>""")
    aggregate_block = (
        f"<p><b>Aggregate parity ({metric_key}):</b> {aggregate}</p>"
        if aggregate is not None else
        "<p>No parity metric available — install scikit-image or imagehash.</p>"
    )
    return f"""<!doctype html>
<html><head><title>Visual diff</title>
<style>body{{font-family:system-ui;padding:20px}}table{{border-collapse:collapse;width:100%}}td{{border:1px solid #ccc;padding:8px;vertical-align:top}}</style>
</head><body>
<h1>Visual diff — input ↔ output</h1>
{aggregate_block}
<table>
<tr><th>#</th><th>Input</th><th>Output</th><th>{metric_key}</th></tr>
{"".join(rows)}
</table>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare input deck PNGs vs rendered .pptx output.")
    parser.add_argument("--input-pngs", nargs="+", required=True,
                        help="Input PNG paths (one per slide)")
    parser.add_argument("--output-pptx", required=True,
                        help="Rendered .pptx to compare against")
    parser.add_argument("--out-dir", default="/tmp/slide-publisher-visual-diff",
                        help="Output directory for rendered PNGs and HTML")
    args = parser.parse_args()

    input_pngs = [Path(p).expanduser() for p in args.input_pngs]
    output_pptx = Path(args.output_pptx).expanduser()
    out_dir = Path(args.out_dir).expanduser()

    try:
        result = diff(input_pngs, output_pptx, out_dir)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    print(f"\nHTML report: {result['html_report']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
