"""
iterate_to_parity.py — iterate the render-diff-adjust loop until visual
parity converges or max_iterations is hit.

Inputs:
    input_pngs:    list of input slide PNGs (the reference)
    ir_path:       Deck IR YAML
    profile_path:  initial template profile YAML
    max_iterations: convergence cap (default 5)
    parity_target:  SSIM/phash threshold to declare convergence (default 0.85)

Pipeline per iteration:
    1. Render IR + profile → output .pptx
    2. visual_diff → per-slide parity scores
    3. Diagnose lowest-parity slide → propose profile adjustment
    4. Apply adjustment → re-iterate

Emits an iteration log naming each adjustment and the parity progression.

v0.1 adjustments supported:
    - Swap layout_map for the offending slide's intent to the next-best
      alternative in the documented fallback chain.

v0.2 will add:
    - Style-token adjustments based on color/font drift.
    - Per-slide layout overrides.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml missing. pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# Anomaly classifier — consume its findings to drive deterministic fixes
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from visual_anomaly_diagnose import diagnose as classify_anomalies
except Exception:
    classify_anomalies = None  # graceful degradation; v0.1 loop still runs


# Same fallback chain as the renderer
LAYOUT_FALLBACKS: dict[str, list[str]] = {
    "title": ["callout", "claim_with_evidence"],
    "section_break": ["callout", "claim_with_evidence"],
    "claim_with_evidence": ["callout"],
    "three_pillars": ["claim_with_evidence", "callout"],
    "comparison": ["claim_with_evidence", "three_pillars"],
    "quote": ["callout", "claim_with_evidence"],
    "image_with_caption": ["claim_with_evidence"],
    "metrics": ["three_pillars", "claim_with_evidence"],
    "timeline": ["claim_with_evidence", "three_pillars"],
    "callout": ["claim_with_evidence"],
}


@dataclass
class IterationLog:
    started_at: str = ""
    finished_at: str = ""
    target: float = 0.85
    max_iterations: int = 5
    converged: bool = False
    iterations: list[dict[str, Any]] = field(default_factory=list)


def run_renderer(ir_path: Path, profile_path: Path, out_path: Path) -> None:
    here = Path(__file__).resolve().parent
    subprocess.run(
        [sys.executable, str(here / "pptx_renderer.py"),
         "--ir", str(ir_path),
         "--profile", str(profile_path),
         "--out", str(out_path)],
        capture_output=True, text=True, check=True,
    )


def run_diff(input_pngs: list[Path], out_pptx: Path, out_dir: Path) -> dict[str, Any]:
    here = Path(__file__).resolve().parent
    cmd = [
        sys.executable, str(here / "visual_diff.py"),
        "--input-pngs", *[str(p) for p in input_pngs],
        "--output-pptx", str(out_pptx),
        "--out-dir", str(out_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"visual_diff failed: {result.stderr}")
    # The script prints summary then "HTML report:" line; parse first JSON block
    out = result.stdout
    end = out.find("\n\nHTML report:")
    if end < 0:
        end = len(out)
    return json.loads(out[:end])


def diagnose_lowest_pair(diff_result: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any] | None:
    pairs = diff_result.get("per_pair", [])
    metric = diff_result.get("metric_key", "ssim")
    if not pairs:
        return None
    lowest = min(pairs, key=lambda p: p.get(metric, 1.0))
    idx = pairs.index(lowest)
    slides = ir.get("slides", [])
    if idx >= len(slides):
        return None
    slide = slides[idx]
    return {
        "slide_idx": idx,
        "slide_id": slide.get("id", ""),
        "intent": slide.get("layout_intent", ""),
        "parity": lowest.get(metric, 0),
        "rationale": (
            f"Slide {idx+1} ({slide.get('id', '')}) has the lowest visual parity "
            f"({metric}={lowest.get(metric, 'n/a')}). Adjusting its layout."
        ),
    }


def adjust_profile(profile: dict[str, Any], diagnosis: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Swap the offending intent's layout_map entry to the next fallback."""
    intent = diagnosis.get("intent", "")
    pptx_branch = profile.get("templates", {}).get("pptx", {})
    layout_map = pptx_branch.get("layout_map", {})
    fallbacks = LAYOUT_FALLBACKS.get(intent, [])
    if not fallbacks:
        return profile, {"adjustment": "no_op", "reason": "no fallback chain"}
    current = layout_map.get(intent)
    next_alt = None
    for alt in fallbacks:
        candidate = layout_map.get(alt)
        if candidate and candidate != current:
            next_alt = candidate
            break
    if not next_alt:
        return profile, {"adjustment": "no_op", "reason": "no alternative found"}
    layout_map[intent] = next_alt
    return profile, {
        "adjustment": "layout_remap",
        "intent": intent,
        "before": current,
        "after": next_alt,
    }


def apply_deterministic_fix(ir: dict[str, Any], anomaly: dict[str, Any],
                            slide_idx: int) -> dict[str, Any] | None:
    """Apply one auto-remediator fix derived from a classifier finding.
    Returns the audit entry, or None if the fix isn't deterministic / failed.
    Mutates IR in place when the fix applies to it.
    """
    if not anomaly.get("deterministic_fix"):
        return None
    payload = anomaly.get("fix_payload", {})
    action = payload.get("action")
    slides = ir.get("slides", [])
    if slide_idx >= len(slides):
        return None
    slide = slides[slide_idx]

    if action == "shorten_ir_title":
        # Trim the IR title to the max_chars_hint, preserving word boundaries.
        max_chars = payload.get("max_chars_hint", 32)
        current = slide.get("title", "")
        if len(current) <= max_chars:
            return {"applied": False, "reason": "title already short enough"}
        # Truncate at word boundary
        truncated = current[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.6:
            truncated = truncated[:last_space]
        truncated = truncated.rstrip() + "…"
        slide["title"] = truncated
        return {
            "applied": True,
            "action": action,
            "field": "slides[].title",
            "before": current,
            "after": truncated,
            "rationale": anomaly.get("finding", ""),
        }

    # Other actions (review_*) are non-deterministic; just log
    return {
        "applied": False,
        "action": action,
        "reason": f"action '{action}' is non-deterministic — surface for human review",
    }


def iterate(input_pngs: list[Path], ir_path: Path, profile_path: Path,
            out_dir: Path, max_iterations: int, parity_target: float) -> IterationLog:
    log = IterationLog(
        started_at=dt.datetime.now().isoformat(timespec="seconds"),
        target=parity_target,
        max_iterations=max_iterations,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    ir = yaml.safe_load(ir_path.read_text())
    profile = yaml.safe_load(profile_path.read_text())

    for i in range(max_iterations):
        iter_dir = out_dir / f"iter-{i+1:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        # 1. Render with current profile
        current_profile_path = iter_dir / "profile.yaml"
        current_profile_path.write_text(yaml.safe_dump(profile, sort_keys=False))
        out_pptx = iter_dir / "rendered.pptx"
        run_renderer(ir_path, current_profile_path, out_pptx)

        # 2. Visual diff
        diff = run_diff(input_pngs, out_pptx, iter_dir / "diff")
        aggregate = diff.get("aggregate_parity")

        entry: dict[str, Any] = {
            "iteration": i + 1,
            "aggregate_parity": aggregate,
            "rendered_at": str(out_pptx),
            "diff_html": diff.get("html_report"),
        }

        # 3. Convergence check
        if aggregate is not None and aggregate >= parity_target:
            log.converged = True
            entry["status"] = "converged"
            log.iterations.append(entry)
            break

        # 4. Diagnose + adjust — TWO-LEVEL strategy:
        #    a) Run anomaly classifier on the lowest-parity pair's per-region diff.
        #       Apply any deterministic fix it surfaces (e.g., shorten title).
        #    b) If no deterministic fix applies, fall back to v0.1 layout swap.
        diag = diagnose_lowest_pair(diff, ir)
        if not diag:
            entry["status"] = "no_diagnosis_possible"
            log.iterations.append(entry)
            break
        slide_idx = diag.get("slide_idx", 0)
        per_pair = diff.get("per_pair", [])
        applied_fixes = []
        anomalies_seen = []
        if classify_anomalies and slide_idx < len(per_pair):
            cls = classify_anomalies(per_pair[slide_idx])
            anomalies_seen = cls.get("anomalies", [])
            for an in anomalies_seen:
                fix_entry = apply_deterministic_fix(ir, an, slide_idx)
                if fix_entry and fix_entry.get("applied"):
                    applied_fixes.append(fix_entry)
                    break  # one fix per iteration — re-render to evaluate
        entry["anomalies"] = anomalies_seen
        entry["applied_fixes"] = applied_fixes
        entry["diagnosis"] = diag
        if applied_fixes:
            # IR mutated; persist for the next iteration's render step
            ir_path = iter_dir / "ir.yaml"
            ir_path.write_text(yaml.safe_dump(ir, sort_keys=False))
            entry["status"] = "iterating_via_deterministic_fix"
            log.iterations.append(entry)
            continue
        # Fallback: try the v0.1 layout-fallback swap on the profile
        profile, adjustment = adjust_profile(profile, diag)
        entry["adjustment"] = adjustment
        entry["status"] = "iterating_via_layout_swap"
        log.iterations.append(entry)

        if adjustment.get("adjustment") == "no_op":
            entry["status"] = "exhausted_adjustments"
            break

    log.finished_at = dt.datetime.now().isoformat(timespec="seconds")
    return log


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Iterate render-diff-adjust loop until visual parity converges.")
    parser.add_argument("--input-pngs", nargs="+", required=True)
    parser.add_argument("--ir", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out-dir", default="/tmp/slide-publisher-iterate")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--parity-target", type=float, default=0.85)
    args = parser.parse_args()

    input_pngs = [Path(p).expanduser() for p in args.input_pngs]
    ir_path = Path(args.ir).expanduser()
    profile_path = Path(args.profile).expanduser()
    out_dir = Path(args.out_dir).expanduser()

    try:
        log = iterate(input_pngs, ir_path, profile_path, out_dir,
                      args.max_iterations, args.parity_target)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(json.dumps({
        "started_at": log.started_at,
        "finished_at": log.finished_at,
        "target": log.target,
        "max_iterations": log.max_iterations,
        "converged": log.converged,
        "iterations": log.iterations,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
