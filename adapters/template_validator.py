"""
template_validator.py — structural quality check for slide-publisher templates.

Inputs:
    template_path_or_key: path to .pptx OR Figma file key.
    fmt: "pptx" or "figma".
    strict: if True, any red finding → verdict "fail". Default: red → fail,
            yellow → warn, all-green → pass.

Outputs a findings report:
    {
        "format": "pptx" | "figma",
        "verdict": "pass" | "warn" | "fail",
        "summary": {"green": N, "yellow": N, "red": N},
        "findings": [
            {
                "criterion": <name>,
                "severity": "green" | "yellow" | "red",
                "value": <raw measurement>,
                "message": "...",
                "remediation": "..." | null,
            },
            ...
        ],
    }

Six criteria (per scope.md § "Quality criteria for templates"):

1. layout_catalog_completeness — fraction of IR layout intents that have a
   matching layout in the template.
2. style_hierarchy — whether heading / body / emphasis style roles are defined.
3. master_usage — single master (clean) vs multiple masters (fragmented).
4. color_tokens — named/tokenized colors vs scattered hex.
5. type_tokens — tokenized font sizes / weights.
6. orphan_elements — layouts that exist but don't map to any IR intent.

Anonymity: this validator ships in the public plugin. Heuristics are generic,
no user-specific data, no organization-specific patterns.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    LAYOUT_INTENTS, INTENT_PATTERNS, infer_layout_map,
    severity_from_fraction as _severity_from_fraction,
    severity_from_count as _severity_from_count,
)

try:
    from pptx import Presentation
except ImportError:
    Presentation = None  # type: ignore


# ---- pptx validator ------------------------------------------------------

def _infer_layout_map(layouts: list[str]) -> dict[str, str]:
    """Wrapper to keep call sites unchanged after factoring to _common."""
    return infer_layout_map(layouts)


def validate_pptx(template_path: str | Path) -> dict[str, Any]:
    """Run all six criteria against a .pptx template."""
    if Presentation is None:
        return {
            "format": "pptx",
            "verdict": "fail",
            "summary": {"green": 0, "yellow": 0, "red": 1},
            "findings": [{
                "criterion": "dependency",
                "severity": "red",
                "value": None,
                "message": "python-pptx is not installed.",
                "remediation": "pip install python-pptx",
            }],
        }

    prs = Presentation(str(template_path))

    # Collect layouts across masters
    all_layouts: list[tuple[int, str]] = []  # (master_idx, layout_name)
    for mi, master in enumerate(prs.slide_masters):
        for layout in master.slide_layouts:
            all_layouts.append((mi, layout.name))
    layout_names = [name for _, name in all_layouts]

    # Map to IR intents
    layout_map = _infer_layout_map(layout_names)

    findings: list[dict[str, Any]] = []

    # 1. Layout-catalog completeness
    coverage = len(layout_map) / len(LAYOUT_INTENTS)
    sev = _severity_from_fraction(coverage, green_at=1.0, yellow_at=0.7)  # explicit kwargs
    missing = [i for i in LAYOUT_INTENTS if i not in layout_map]
    findings.append({
        "criterion": "layout_catalog_completeness",
        "severity": sev,
        "value": f"{len(layout_map)}/{len(LAYOUT_INTENTS)}",
        "message": (
            f"{len(layout_map)} of {len(LAYOUT_INTENTS)} IR layout intents have a "
            f"matching pptx layout."
        ),
        "remediation": (
            f"Add layouts for: {', '.join(missing)}. Or set "
            f"`layout_map` overrides in profile.yaml to point existing layouts "
            f"at these intents."
        ) if missing else None,
    })

    # 2. Style hierarchy — count of distinct font sizes in master XML
    sizes: Counter[int] = Counter()
    fonts: Counter[str] = Counter()
    for master in prs.slide_masters:
        for el in master.element.iter():
            tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
            if tag == "rPr":
                sz = el.get("sz")
                if sz and sz.isdigit():
                    sizes[int(sz) // 100] += 1
            elif tag == "latin":
                tf = el.get("typeface")
                if tf and not tf.startswith("+"):
                    fonts[tf] += 1
    n_size_levels = len({s for s, _ in sizes.most_common() if s > 0})
    sev = _severity_from_count(n_size_levels, green_at=4, yellow_at=2)
    findings.append({
        "criterion": "style_hierarchy",
        "severity": sev,
        "value": n_size_levels,
        "message": (
            f"{n_size_levels} distinct font size levels found in the slide "
            f"master(s) (heading-1, body, caption tiers, etc.)."
        ),
        "remediation": (
            "Define explicit font-size tokens for heading, body, and caption "
            "tiers in the slide master. Without a hierarchy, renderers can't "
            "infer emphasis from the IR's beat structure."
        ) if sev != "green" else None,
    })

    # 3. Master usage — single master is clean; multiple is fragmented
    n_masters = len(prs.slide_masters)
    sev = "green" if n_masters == 1 else ("yellow" if n_masters == 2 else "red")
    findings.append({
        "criterion": "master_usage",
        "severity": sev,
        "value": n_masters,
        "message": f"{n_masters} slide master{'s' if n_masters != 1 else ''} in this template.",
        "remediation": (
            "Consolidate to a single master. Multi-master decks fragment style "
            "inheritance — renderers see inconsistent base styles across slides."
        ) if sev != "green" else None,
    })

    # 4. Color tokens
    colors: Counter[str] = Counter()
    for master in prs.slide_masters:
        for el in master.element.iter():
            tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
            if tag == "srgbClr":
                val = el.get("val")
                if val and len(val) == 6:
                    colors[f"#{val.upper()}"] += 1
    n_color_tokens = len(colors)
    sev = _severity_from_count(n_color_tokens, green_at=4, yellow_at=2)
    findings.append({
        "criterion": "color_tokens",
        "severity": sev,
        "value": n_color_tokens,
        "message": (
            f"{n_color_tokens} explicit color(s) defined in master XML. "
            f"(Note: theme colors aren't counted here — they may inflate the "
            f"effective palette beyond this number.)"
        ),
        "remediation": (
            "Define brand colors as explicit tokens in your theme or master. "
            "Scattered hex values across slides make consistent rendering hard."
        ) if sev == "red" else None,
    })

    # 5. Type tokens — distinct typeface families
    n_typefaces = len(fonts)
    sev = _severity_from_count(n_typefaces, green_at=1, yellow_at=1)
    # Special case: if 0 typefaces extracted, that's typically theme-only — yellow not red
    if n_typefaces == 0:
        sev = "yellow"
    elif n_typefaces > 3:
        sev = "yellow"  # too many typefaces is also a yellow signal
    findings.append({
        "criterion": "type_tokens",
        "severity": sev,
        "value": n_typefaces,
        "message": (
            f"{n_typefaces} typeface(s) explicitly named in master XML. "
            f"({fonts.most_common(3) if fonts else 'theme-only typography'})"
        ),
        "remediation": (
            "Pick 1-2 typefaces (display + body) and define them as tokens. "
            ">3 typefaces creates visual noise."
        ) if sev == "yellow" else None,
    })

    # 6. Orphan layouts — layouts that don't map to any IR intent
    orphan_layouts = [name for name in layout_names if name not in layout_map.values()]
    n_orphans = len(orphan_layouts)
    orphan_frac = n_orphans / len(layout_names) if layout_names else 0.0
    if orphan_frac < 0.2:
        sev = "green"
    elif orphan_frac < 0.5:
        sev = "yellow"
    else:
        sev = "red"
    findings.append({
        "criterion": "orphan_elements",
        "severity": sev,
        "value": f"{n_orphans} of {len(layout_names)}",
        "message": (
            f"{n_orphans} layout(s) in the template don't map to any IR intent: "
            f"{', '.join(orphan_layouts[:5])}"
            + ("..." if len(orphan_layouts) > 5 else "")
        ),
        "remediation": (
            "Review orphan layouts — they may be unused legacy patterns or "
            "specialized layouts the IR doesn't cover yet. Either remove them "
            "or extend the IR catalog (v0.2 scoping pass)."
        ) if sev != "green" else None,
    })

    return _finalize(findings, fmt="pptx")


# ---- figma validator -----------------------------------------------------

def validate_figma(file_key: str, profile_entry: dict | None = None) -> dict[str, Any]:
    """v0.1 stub. Figma validation requires live Figma MCP access (api.figma.com
    is sandbox-allowlisted but the validator runs in the user's Cowork session).

    For v0.1, this validator path expects an upstream `template-extractor-figma`
    invocation to populate `profile_entry`, then runs whatever criteria can be
    checked statically from that entry. Live structural inspection (master
    fragmentation, orphan node detection) is deferred to v0.2.
    """
    findings: list[dict[str, Any]] = []

    if profile_entry is None:
        findings.append({
            "criterion": "dependency",
            "severity": "red",
            "value": file_key,
            "message": (
                "Figma template validation requires an extractor-produced "
                "profile entry as input. Call template-extractor-figma first."
            ),
            "remediation": (
                "Run `template-extractor-figma <file_key>` and pass the "
                "resulting profile entry to this validator."
            ),
        })
        return _finalize(findings, fmt="figma")

    # 1. Layout-catalog completeness — from extractor's layout_map
    layout_map = profile_entry.get("layout_map", {})
    coverage = len(layout_map) / len(LAYOUT_INTENTS)
    sev = _severity_from_fraction(coverage, green_at=1.0, yellow_at=0.7)  # explicit kwargs
    missing = [i for i in LAYOUT_INTENTS if i not in layout_map]
    findings.append({
        "criterion": "layout_catalog_completeness",
        "severity": sev,
        "value": f"{len(layout_map)}/{len(LAYOUT_INTENTS)}",
        "message": f"{len(layout_map)} of {len(LAYOUT_INTENTS)} IR intents mapped.",
        "remediation": (
            f"Add Figma slide templates for: {', '.join(missing)}. Tag each "
            f"with a Heading frame whose text matches the intent name "
            f"(per cos-figma-publish-chain Rule 2 — identify by title text)."
        ) if missing else None,
    })

    # 4. Color tokens (from extractor)
    style_tokens = profile_entry.get("style_tokens", {})
    colors = style_tokens.get("colors", {})
    sev = _severity_from_count(len(colors), green_at=4, yellow_at=2)
    findings.append({
        "criterion": "color_tokens",
        "severity": sev,
        "value": len(colors),
        "message": f"{len(colors)} color tokens extracted from Figma styles.",
        "remediation": (
            "Define color styles in Figma (Figma → Styles → Colors). Locally-"
            "applied colors won't appear as tokens."
        ) if sev == "red" else None,
    })

    # 5. Type tokens
    typography = style_tokens.get("typography", {})
    sev = _severity_from_count(len(typography), green_at=3, yellow_at=1)
    findings.append({
        "criterion": "type_tokens",
        "severity": sev,
        "value": len(typography),
        "message": f"{len(typography)} type tokens extracted from Figma text styles.",
        "remediation": (
            "Define text styles in Figma (Figma → Styles → Text). Without "
            "named text styles, renderers can't infer hierarchy from the IR."
        ) if sev != "green" else None,
    })

    # 2, 3, 6 deferred to v0.2 (live structural inspection)
    findings.append({
        "criterion": "live_structural_checks",
        "severity": "yellow",
        "value": None,
        "message": (
            "Live structural checks (style_hierarchy, master_usage, "
            "orphan_elements) are deferred to v0.2 for Figma templates. "
            "Run them manually for now via the Figma plugin inspector."
        ),
        "remediation": None,
    })

    return _finalize(findings, fmt="figma")


# ---- Reporting -----------------------------------------------------------

def _finalize(findings: list[dict[str, Any]], fmt: str) -> dict[str, Any]:
    severities = [f["severity"] for f in findings]
    summary = {
        "green": severities.count("green"),
        "yellow": severities.count("yellow"),
        "red": severities.count("red"),
    }
    if summary["red"] > 0:
        verdict = "fail"
    elif summary["yellow"] > 0:
        verdict = "warn"
    else:
        verdict = "pass"
    return {
        "format": fmt,
        "verdict": verdict,
        "summary": summary,
        "findings": findings,
    }


def validate(target: str, fmt: str, profile_entry: dict | None = None) -> dict[str, Any]:
    if fmt == "pptx":
        return validate_pptx(target)
    elif fmt == "figma":
        return validate_figma(target, profile_entry)
    else:
        raise ValueError(f"Unknown format: {fmt}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a slide-publisher template against the 6-criteria quality "
            "rubric. Emits a green/yellow/red findings report with per-finding "
            "remediation."
        )
    )
    parser.add_argument("target", help="Path to .pptx (or Figma file key)")
    parser.add_argument("--format", choices=["pptx", "figma"], required=True)
    parser.add_argument("--profile-entry", help="Path to a JSON profile-entry (for Figma).")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on any yellow finding. Default: only red fails.")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    profile_entry = None
    if args.profile_entry:
        profile_entry = json.loads(Path(args.profile_entry).read_text())

    report = validate(args.target, args.format, profile_entry)

    out_text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(out_text + "\n")
    else:
        print(out_text)

    if args.strict and report["verdict"] != "pass":
        return 1
    if report["verdict"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
