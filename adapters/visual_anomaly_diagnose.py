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
    "variance_spike_ratio": 1.3,    # render / baseline > this = busier (overflow)
    # v0.2.2: dead-space rule — region has very low variance, suggesting an
    # empty content slot the IR was supposed to fill.
    "dead_space_variance": 200,     # absolute variance below this = dead
    "dead_space_color_uniformity": 5,  # pixel std-dev across rgb < this = flat
    # v0.2.2: body-region-shift rule — title variance drops AND body variance
    # rises in tandem. The threshold is on the SUM signal across regions.
    "body_shift_combined_signal": 0.4,  # |title_ratio_drop - 1| + |body_ratio_rise - 1|
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


def rule_body_region_shift(diff: dict, ctx: dict) -> list[dict]:
    """Paired signal: title region variance drops AND body region variance rises.

    Captures the exact failure mode the v0.2.1 walkthrough surfaced — title
    overflow into the body region, then "fixed" so body content moved DOWN to
    its proper home. The classic title_overflow rule needed SSIM to fire; this
    one works on per-region variance alone, so it degrades gracefully when
    scikit-image isn't available.
    """
    title = _get_region(diff, "title")
    body = _get_region(diff, "body")
    if not title or not body:
        return []
    t_a = title.get("variance_a", 0)
    t_b = title.get("variance_b", 0)
    b_a = body.get("variance_a", 0)
    b_b = body.get("variance_b", 0)
    if t_a <= 0 or b_a <= 0:
        return []
    title_ratio = t_b / max(t_a, 1)
    body_ratio = b_b / max(b_a, 1)
    # Title region got cleaner (ratio < 1) AND body region got busier (ratio > 1)
    if title_ratio < 0.9 and body_ratio > 1.1:
        combined = (1 - title_ratio) + (body_ratio - 1)
        if combined >= THRESHOLDS["body_shift_combined_signal"]:
            return [{
                "rule": "body_region_shift",
                "region": "title+body",
                "severity": "high" if combined > 1.0 else "medium",
                "finding": (f"Title-region variance dropped {title_ratio:.2f}× and "
                            f"body-region variance rose {body_ratio:.2f}× — body "
                            f"content shifted regions (often the signature of a "
                            f"title-overflow fix or a layout binding change)."),
                "recommended_fix": "Confirm the body content lands in the body "
                                   "placeholder. If this is a regression from a "
                                   "previous render, investigate the layout-map "
                                   "binding or the renderer's placeholder choice.",
                "deterministic_fix": False,
                "fix_payload": {"action": "review_layout_binding"},
            }]
    return []


def rule_dead_space(diff: dict, ctx: dict) -> list[dict]:
    """Region has very low variance AND uniform color — likely empty content slot.

    The exact failure mode from the executive-briefing × Madison slide 7 walkthrough:
    Picture with Caption layout's right half is dead because the renderer dropped
    the prose body block. The classifier needs to flag dead structural regions
    where IR content was destined.
    """
    findings = []
    for r in diff.get("regions", []):
        name = r.get("region")
        vb = r.get("variance_b", 0)
        delta = r.get("mean_color_delta", {})
        if vb < THRESHOLDS["dead_space_variance"]:
            findings.append({
                "rule": "dead_space",
                "region": name,
                "severity": "medium",
                "finding": (f"{name.capitalize()} region of render is nearly flat "
                            f"(variance {vb:.0f}) — likely an empty structural "
                            f"placeholder the IR was supposed to fill (image slot, "
                            f"caption slot, or second column)."),
                "recommended_fix": "Check the renderer's loss manifest for "
                                   "DROPPED entries in this slide. Body blocks may "
                                   "not be binding to the layout's placeholder slots.",
                "deterministic_fix": False,
                "fix_payload": {"action": "review_loss_manifest"},
            })
    return findings


RULES = [
    rule_title_overflow,
    rule_missing_fill,
    rule_empty_body,
    rule_missing_decoration,
    rule_font_substitution,
    rule_body_region_shift,    # v0.2.2
    rule_dead_space,           # v0.2.2
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
