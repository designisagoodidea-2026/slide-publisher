"""
tests/visual-qa/run_renders.py — render harness for visual QA.

Matrix runner over (IR, template, renderer) tuples. For each combination:
  1. Run the appropriate renderer to produce .pptx (and in future, .figma.yaml).
  2. Convert each output to per-slide PNGs (LibreOffice → PDF → pdftoppm).
  3. Compare each PNG against a baseline (baselines.yaml) using SSIM + pHash
     via adapters/visual_diff.py.
  4. Emit a structured report — pass / regression / new (no baseline yet).

Output layout:
    tests/visual-qa/runs/<timestamp>/
        <ir-stem>/
            <template-stem>/
                pptx/
                    render.pptx
                    slide-1.png
                    slide-2.png
                    ...
                    diff-report.md      (if baseline exists)
                    diff-report.json
        summary.md
        summary.json

Baseline capture mode (`--capture-baseline`): copies the run output
into tests/visual-qa/baselines/<key>/ and writes baselines.yaml entries.

Scope:
  - PPTX path is fully automated (renderer + LibreOffice).
  - Figma path requires MCP access — not automatable from this harness.
    Figma visual QA runs as a chat-mediated step (use_figma + get_screenshot).
    Logged for v0.2.x: an MCP-aware harness mode that emits a publish-payload
    + screenshot-payload script the user runs in chat.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parent.parent.parent  # plugin/
ADAPTERS = ROOT / "adapters"
PROJECT_ROOT = ROOT.parent  # /Slide Publisher/
QA_DIR = ROOT / "tests" / "visual-qa"
RUNS_DIR = QA_DIR / "runs"
BASELINES_DIR = QA_DIR / "baselines"
BASELINES_YAML = QA_DIR / "baselines.yaml"


@dataclass
class Tuple:
    ir_path: Path
    template_path: Path
    renderer: str  # "pptx" for now

    @property
    def key(self) -> str:
        return f"{self.ir_path.stem}__{self.template_path.stem}__{self.renderer}"


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       cwd=str(cwd) if cwd else None)
    return r.returncode, r.stdout, r.stderr


def find_libreoffice() -> str | None:
    for c in ("libreoffice", "soffice"):
        p = shutil.which(c)
        if p:
            return p
    macos = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return macos if Path(macos).exists() else None


def find_pdftoppm() -> str | None:
    return shutil.which("pdftoppm")


# ============================================================================
# Render + slice steps
# ============================================================================

def extract_template_profile(template_pptx: Path, out_dir: Path) -> Path | None:
    """Run template-extractor-pptx → produce profile YAML wrapping the layout map."""
    entry_json = out_dir / f"{template_pptx.stem}.profile-entry.json"
    code, out, err = _run([
        "python3", str(ADAPTERS / "template_extractor_pptx.py"),
        str(template_pptx), "--out", str(entry_json), "--strip-debug",
    ])
    if code != 0:
        return None
    entry = json.loads(entry_json.read_text())
    profile = {
        "profile_version": "1.0.0",
        "preferred_output": "pptx",
        "templates": {
            "pptx": {
                "path": str(template_pptx),
                "layout_map": entry.get("layout_map", {}),
                "quality_score": entry.get("quality_score", 0),
            },
        },
        "style_tokens": entry.get("style_tokens", {}),
    }
    yaml_path = out_dir / f"{template_pptx.stem}.profile.yaml"
    yaml_path.write_text(yaml.safe_dump(profile, sort_keys=False))
    return yaml_path


def render_pptx(ir: Path, profile_yaml: Path, out_dir: Path) -> Path | None:
    out_pptx = out_dir / "render.pptx"
    code, out, err = _run([
        "python3", str(ADAPTERS / "pptx_renderer.py"),
        "--ir", str(ir), "--profile", str(profile_yaml), "--out", str(out_pptx),
    ])
    if code != 0:
        sys.stderr.write(f"  render failed: {err}\n")
        return None
    return out_pptx


def pptx_to_pngs(pptx: Path, out_dir: Path, dpi: int = 100) -> list[Path]:
    soffice = find_libreoffice()
    pdftoppm = find_pdftoppm()
    if not soffice or not pdftoppm:
        sys.stderr.write(f"  LibreOffice ({bool(soffice)}) or pdftoppm ({bool(pdftoppm)}) missing\n")
        return []
    code, _, err = _run([soffice, "--headless", "--convert-to", "pdf",
                        str(pptx), "--outdir", str(out_dir)], timeout=180)
    if code != 0:
        sys.stderr.write(f"  soffice convert failed: {err}\n")
        return []
    pdf = out_dir / pptx.with_suffix(".pdf").name
    code, _, err = _run([pdftoppm, str(pdf), str(out_dir / "slide"),
                        "-png", "-r", str(dpi)])
    if code != 0:
        sys.stderr.write(f"  pdftoppm failed: {err}\n")
        return []
    return sorted(out_dir.glob("slide-*.png"))


# ============================================================================
# Baseline diff (lightweight; full diff engine lives in adapters/visual_diff.py)
# ============================================================================

def png_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def compare_against_baseline(slide_png: Path, baseline_png: Path,
                             ssim_threshold: float = 0.92) -> dict:
    """Two-tier comparison: byte-hash first (cheap, fast); if drifted,
    upgrade to SSIM via adapters/visual_diff. SSIM < threshold = regression.
    """
    if not baseline_png.exists():
        return {"status": "no_baseline"}
    h_now = png_hash(slide_png)
    h_base = png_hash(baseline_png)
    if h_now == h_base:
        return {"status": "identical", "hash": h_now}
    # Drifted — get the real similarity score
    try:
        sys.path.insert(0, str(ROOT / "adapters"))
        from visual_diff import compare_pair as _vd_compare
        diff = _vd_compare(baseline_png, slide_png)
        ssim_score = diff.get("ssim")
        phash_sim = diff.get("phash_similarity")
        if ssim_score is None and phash_sim is None:
            # No similarity metric available — fall back to byte drift report
            return {"status": "drift", "hash_now": h_now, "hash_baseline": h_base,
                    "ssim_unavailable": True}
        metric = ssim_score if ssim_score is not None else phash_sim
        status = "pass" if metric >= ssim_threshold else "regression"
        return {
            "status": status,
            "ssim": ssim_score,
            "phash_similarity": phash_sim,
            "threshold": ssim_threshold,
            "regions": diff.get("regions"),
        }
    except Exception as e:
        return {"status": "diff_failed", "error": str(e)[:200],
                "hash_now": h_now, "hash_baseline": h_base}


# ============================================================================
# Matrix runner
# ============================================================================

def collect_tuples(ir_dir: Path, templates: list[Path]) -> list[Tuple]:
    tuples = []
    for ir in sorted(ir_dir.glob("*.yaml")):
        for tpl in templates:
            tuples.append(Tuple(ir_path=ir, template_path=tpl, renderer="pptx"))
    return tuples


def load_baselines() -> dict:
    if not BASELINES_YAML.exists():
        return {}
    return yaml.safe_load(BASELINES_YAML.read_text()) or {}


def write_baselines(baselines: dict) -> None:
    BASELINES_YAML.write_text(yaml.safe_dump(baselines, sort_keys=True))


def capture_baseline_from_run(run_root: Path) -> int:
    """Copy a run's PNG outputs into baselines/<key>/ and write baselines.yaml."""
    baselines = load_baselines()
    # Drop stale entries from prior runs (lockfile names like '~$foo')
    baselines = {k: v for k, v in baselines.items() if "~$" not in k}
    captured = 0
    for tuple_dir in run_root.iterdir():
        if not tuple_dir.is_dir() or tuple_dir.name.startswith("~"):
            continue
        for template_dir in tuple_dir.iterdir():
            if template_dir.name.startswith("~"):
                continue
            for renderer_dir in template_dir.iterdir():
                key = f"{tuple_dir.name}__{template_dir.name}__{renderer_dir.name}"
                pngs = sorted(renderer_dir.glob("slide-*.png"))
                if not pngs:
                    continue
                bdir = BASELINES_DIR / key
                bdir.mkdir(parents=True, exist_ok=True)
                slide_baselines = []
                for png in pngs:
                    dest = bdir / png.name
                    shutil.copy2(png, dest)
                    slide_baselines.append({
                        "slide": png.name,
                        "sha256_16": png_hash(dest),
                        "size_bytes": dest.stat().st_size,
                    })
                baselines[key] = {
                    "captured_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "n_slides": len(pngs),
                    "slides": slide_baselines,
                    "ssim_threshold": 0.92,  # default; tune per-render
                }
                captured += 1
    write_baselines(baselines)
    return captured


def run_one(t: Tuple, run_root: Path, baselines: dict) -> dict:
    print(f"  rendering {t.key}…")
    tdir = run_root / t.ir_path.stem / t.template_path.stem / t.renderer
    tdir.mkdir(parents=True, exist_ok=True)
    profile = extract_template_profile(t.template_path, tdir)
    if not profile:
        return {"key": t.key, "status": "extract_failed"}
    rendered = render_pptx(t.ir_path, profile, tdir)
    if not rendered:
        return {"key": t.key, "status": "render_failed"}
    pngs = pptx_to_pngs(rendered, tdir)
    if not pngs:
        return {"key": t.key, "status": "rasterize_failed"}
    baseline_entry = baselines.get(t.key, {})
    ssim_threshold = baseline_entry.get("ssim_threshold", 0.92)
    slide_findings = []
    for png in pngs:
        bdir = BASELINES_DIR / t.key
        baseline_png = bdir / png.name
        cmp = compare_against_baseline(png, baseline_png, ssim_threshold)
        slide_findings.append({"slide": png.name, **cmp})
    regressions = [s for s in slide_findings if s.get("status") == "regression"]
    new = [s for s in slide_findings if s.get("status") == "no_baseline"]
    failed = [s for s in slide_findings if s.get("status") == "diff_failed"]
    return {
        "key": t.key,
        "status": (
            "regression" if regressions else
            "new" if new else
            "diff_failed" if failed else
            "pass"
        ),
        "n_slides": len(pngs),
        "n_regressions": len(regressions),
        "n_new": len(new),
        "n_failed": len(failed),
        "slides": slide_findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--ir-dir", default=str(ROOT / "ir" / "examples"))
    parser.add_argument("--template-dir",
                        default=str(PROJECT_ROOT / "notes" / "microsoft-themes"),
                        help="Folder of .pptx templates")
    parser.add_argument("--capture-baseline", action="store_true",
                        help="Copy this run's PNGs into baselines/")
    parser.add_argument("--keep-runs", type=int, default=5,
                        help="Number of past runs to retain")
    args = parser.parse_args()

    ir_dir = Path(args.ir_dir).expanduser()
    tpl_dir = Path(args.template_dir).expanduser()
    templates = sorted(
        p for p in tpl_dir.glob("*.pptx")
        if not p.name.startswith("~$")  # LibreOffice lockfiles
    ) if tpl_dir.exists() else []
    if not templates:
        print(f"FATAL: no .pptx templates in {tpl_dir}", file=sys.stderr)
        return 2
    tuples = collect_tuples(ir_dir, templates)
    if not tuples:
        print(f"FATAL: no IRs in {ir_dir}", file=sys.stderr)
        return 2

    timestamp = dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    run_root = RUNS_DIR / timestamp
    run_root.mkdir(parents=True, exist_ok=True)

    baselines = load_baselines()
    print(f"\n  Visual QA harness — run {timestamp}")
    print(f"  IRs:        {len(tuples) // len(templates)} × templates: {len(templates)}")
    print(f"  total renders: {len(tuples)}\n")

    summary = []
    for t in tuples:
        summary.append(run_one(t, run_root, baselines))

    (run_root / "summary.json").write_text(json.dumps(summary, indent=2))
    pass_count = sum(1 for s in summary if s["status"] == "pass")
    regression = sum(1 for s in summary if s["status"] == "regression")
    new_count = sum(1 for s in summary if s["status"] == "new")
    failed = sum(1 for s in summary if s["status"] in ("diff_failed", "extract_failed", "render_failed", "rasterize_failed"))
    md_lines = [f"# Visual QA — run {timestamp}\n",
                f"- pass:       {pass_count}",
                f"- regression: {regression}",
                f"- new:        {new_count}",
                f"- failed:     {failed}\n",
                "## Per-tuple findings\n"]
    for s in summary:
        md_lines.append(f"- **{s['key']}** — {s['status']} "
                        f"({s.get('n_slides',0)} slides; "
                        f"{s.get('n_drifts',0)} drifts; {s.get('n_new',0)} new)")
    (run_root / "summary.md").write_text("\n".join(md_lines) + "\n")

    if args.capture_baseline:
        n = capture_baseline_from_run(run_root)
        print(f"\n  Captured {n} baseline(s) → {BASELINES_DIR}")

    # Prune old runs
    runs = sorted(RUNS_DIR.iterdir(), reverse=True)
    for old in runs[args.keep_runs:]:
        if old.is_dir():
            shutil.rmtree(old)

    print(f"\n  Done. {pass_count} pass, {regression} regression, "
          f"{new_count} new, {failed} failed.")
    print(f"  Output:   {run_root}")
    print(f"  Summary:  {run_root / 'summary.md'}")
    return 1 if (regression or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
