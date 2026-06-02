"""
visual_anomaly_diagnose.py — rules-based classifier that maps per-region
visual-diff output into structured anomaly findings.

Input shape (from adapters/visual_diff.compare_pair):
    {
      a, b, ssim, phash_similarity,
      regions: [
        {region, ssim, phash_similarity, mean_color_delta, variance_a, variance_b},
        ...
      ],
    }

Optional context input (when invoked alongside a render):
    {
      ir_slide: {layout_intent, title, body, ...},
      profile_layout: {placeholder_dimensions, expected_fonts, ...},
    }

Output:
    {
      anomalies: [
        {
          rule: "title_overflow" | "missing_fill" | ...,
          region: "title" | "body" | "footer" | "whole",
          severity: "low" | "medium" | "high",
          finding: "<one-line plain-English diagnosis>",
          recommended_fix: "<actionable suggestion>",
          deterministic_fix: bool,   # can auto-remediation apply this?
          fix_payload: {...},        # how the auto-remediator should apply it
        },
        ...
      ],
      summary: { n_high: int, n_medium: int, n_low: int },
    }

v0.1 rules (5):
  - title_overflow: SSIM drop + variance spike in title region
  - missing_fill: large color delta + variance drop in any region
  - empty_body: variance collapse in body region of render
  - missing_decoration: variance drop across all regions vs baseline
  - font_substitution (heuristic): low title-region SSIM with low color delta

Design note: this is rules-based at v0.1. v0.2 may add ML/learned thresholds
once we have enough labeled examples from production runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# Thresholds — tuned against the design-system-retro × atlas-theme baseline.
# v0.2 should make these configurable per (renderer × template) tuple.
THRESHOLDS = {
    "ssim_high_drift": 0.85,       # below this = significant regression
    "ssim_low_drift": 0.92,        # below this = warning
    "color_delta_significant": 30, # magnitude > this = notable color shift
    "color_delta_major": 60,       # magnitude > this = big shift (theme miss)
    "variance_collapse_ratio": 0.3, # render variance / baseline variance < this = empty
    "variance_spike_ratio": 1.5,    # render / baseline > this = busier (overflow)
}


def _get_region(diff: dict, name: str) -> dict | None:
    for r in diff.get("regions", []):
        if r.get("region") == name:
            return r
    return None


# ---------------------------------------------------------------------------
# Rule implementations — each returns a list of findings (0 or more).
# ---------------------------------------------------------------------------

def rule_title_overflow(diff: dict, ctx: dict) -> list[dict]:
    """Title region: SSIM significantly degraded AND variance higher in render."""
    title = _get_region(diff, "title")
    if not title:
        return []
    s = title.get("ssim")
    va = title.get("variance_a")
    vb = title.get("variance_b")
    if s is None or va in (None, 0) or vb is None:
        return []
    ratio = vb / max(va, 1)
    if s < THRESHOLDS["ssim_low_drift"] and ratio > THRESHOLDS["variance_spike_ratio"]:
        sev = "high" if s < THRESHOLDS["ssim_high_drift"] else "medium"
        return [{
            "rule": "title_overflow",
            "region": "title",
            "severity": sev,
            "finding": (f"Title region SSIM dropped to {s} with variance ratio {ratio:.2f}× — "
                        f"text likely overflowing the title placeholder bounds."),
            "recommended_fix": "Shorten the IR title OR pick a less-constrained layout intent.",
            "deterministic_fix": True,
            "fix_payload": {
                "action": "shorten_ir_title",
                "max_chars_hint": 32,
            },
        }]
    return []


def rule_missing_fill(diff: dict, ctx: dict) -> list[dict]:
    """Any region: large color delta AND variance drop = fill was lost."""
    findings = []
    for r in diff.get("regions", []):
        name = r.get("region")
        delta = r.get("mean_color_delta", {})
        mag = delta.get("magnitude", 0)
        va = r.get("variance_a", 0)
        vb = r.get("variance_b", 0)
        if va == 0:
            continue
        ratio = vb / max(va, 1)
        if mag > THRESHOLDS["color_delta_major"] and ratio < THRESHOLDS["variance_collapse_ratio"]:
            findings.append({
                "rule": "missing_fill",
                "region": name,
                "severity": "high",
                "finding": (f"{name.capitalize()} region color shifted by {mag} (magnitude) and "
                            f"variance dropped to {ratio:.2f}× — a fill or shape was likely lost."),
                "recommended_fix": "Verify the renderer preserves non-placeholder shapes "
                                   "and fill_style ids when populating template clones.",
                "deterministic_fix": False,
                "fix_payload": {"action": "review_renderer_fill_preservation"},
            })
    return findings


def rule_empty_body(diff: dict, ctx: dict) -> list[dict]:
    """Body region: variance very low in render, was significant in baseline."""
    body = _get_region(diff, "body")
    if not body:
        return []
    va = body.get("variance_a", 0)
    vb = body.get("variance_b", 0)
    if va == 0:
        return []
    ratio = vb / max(va, 1)
    if ratio < THRESHOLDS["variance_collapse_ratio"] and va > 1000:
        return [{
            "rule": "empty_body",
            "region": "body",
            "severity": "high",
            "finding": (f"Body region nearly empty in render (variance {vb:.0f}, "
                        f"baseline {va:.0f}, ratio {ratio:.2f}×) — body content likely "
                        f"didn't bind to a placeholder."),
            "recommended_fix": "Check the layout's BODY node binding; surface as DROPPED "
                               "in the loss manifest if intentional.",
            "deterministic_fix": False,
            "fix_payload": {"action": "review_body_binding"},
        }]
    return []


def rule_missing_decoration(diff: dict, ctx: dict) -> list[dict]:
    """All regions: render variance noticeably lower across the board."""
    drops = []
    for r in diff.get("regions", []):
        va = r.get("variance_a", 0)
        vb = r.get("variance_b", 0)
        if va < 500:  # baseline was already plain; not a decoration loss
            continue
        ratio = vb / max(va, 1)
        if ratio < 0.5:
            drops.append({"region": r["region"], "ratio": round(ratio, 2)})
    if len(drops) >= 2:
        return [{
            "rule": "missing_decoration",
            "region": "whole",
            "severity": "medium",
            "finding": (f"Variance drop across {len(drops)} regions ({drops}) — "
                        f"decorative template elements may have been stripped."),
            "recommended_fix": "Inspect the renderer's _strip_existing_slides logic; "
                               "decorative shapes (non_placeholder=True) should survive.",
            "deterministic_fix": False,
            "fix_payload": {"action": "review_strip_logic"},
        }]
    return []


def rule_font_substitution(diff: dict, ctx: dict) -> list[dict]:
    """Heuristic: title SSIM low but mean color similar = same layout, different font."""
    title = _get_region(diff, "title")
    if not title:
        return []
    s = title.get("ssim")
    delta = title.get("mean_color_delta", {})
    mag = delta.get("magnitude", 0)
    if s is None:
        return []
    if s < THRESHOLDS["ssim_high_drift"] and mag < THRESHOLDS["color_delta_significant"]:
        return [{
            "rule": "font_substitution",
            "region": "title",
            "severity": "medium",
            "finding": (f"Title SSIM {s} with low color delta ({mag}) — text shape changed "
                        f"but theme didn't; likely font substitution."),
            "recommended_fix": "Verify the template's title font is installed on the render host, "
                               "or fall back to the profile's safe_alternate typeface.",
            "deterministic_fix": False,
            "fix_payload": {"action": "review_font_install"},
        }]
    return []


RULES = [
    rule_title_overflow,
    rule_missing_fill,
    rule_empty_body,
    rule_missing_decoration,
    rule_font_substitution,
]


def diagnose(diff_output: dict, context: dict | None = None) -> dict:
    """Run all rules against a visual_diff output. Returns anomaly list + summary."""
    ctx = context or {}
    anomalies = []
    for rule in RULES:
        try:
            anomalies.extend(rule(diff_output, ctx))
        except Exception as e:
            anomalies.append({
                "rule": rule.__name__,
                "severity": "low",
                "finding": f"rule errored: {e}",
                "recommended_fix": "Investigate classifier; treat anomaly result as missing.",
                "deterministic_fix": False,
            })
    summary = {
        "n_high": sum(1 for a in anomalies if a.get("severity") == "high"),
        "n_medium": sum(1 for a in anomalies if a.get("severity") == "medium"),
        "n_low": sum(1 for a in anomalies if a.get("severity") == "low"),
    }
    return {"anomalies": anomalies, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("diff_json", nargs="?", default="-",
                        help="Path to visual_diff per-pair JSON (or '-' for stdin)")
    parser.add_argument("--context", help="Optional context JSON (IR slide + profile)")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    args = parser.parse_args()
    text = (sys.stdin.read() if args.diff_json == "-"
            else Path(args.diff_json).expanduser().read_text())
    diff_doc = json.loads(text)
    # Accept either a single pair or a "per_pair" envelope from visual_diff.diff()
    if isinstance(diff_doc, dict) and "per_pair" in diff_doc:
        results = [{"pair_index": i, **diagnose(p)}
                   for i, p in enumerate(diff_doc["per_pair"])]
        out_doc = {"per_pair": results}
    else:
        ctx = json.loads(Path(args.context).read_text()) if args.context else None
        out_doc = diagnose(diff_doc, ctx)
    text_out = json.dumps(out_doc, indent=2)
    if args.out:
        Path(args.out).expanduser().write_text(text_out + "\n")
    else:
        print(text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
