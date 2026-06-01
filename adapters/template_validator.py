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
    LAYOUT_INTENTS, INTENT_PATTERNS, infer_layout_map, effective_coverage,
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


def _has_theme_fontscheme(prs) -> bool:
    """True if theme1.xml carries a fontScheme with major/minor typefaces."""
    try:
        for master in prs.slide_masters:
            theme_part = None
            for rel_id, rel in master.part.rels.items():
                if rel.reltype.endswith("/theme"):
                    theme_part = rel.target_part
                    break
            if theme_part is None:
                continue
            xml = theme_part.blob.decode("utf-8", errors="ignore")
            if "majorFont" in xml and "minorFont" in xml:
                return True
    except Exception:
        pass
    return False


def _count_theme_colors(prs) -> int:
    """Number of color tokens defined in theme1.xml clrScheme."""
    import xml.etree.ElementTree as ET
    out = 0
    try:
        for master in prs.slide_masters:
            theme_part = None
            for rel_id, rel in master.part.rels.items():
                if rel.reltype.endswith("/theme"):
                    theme_part = rel.target_part
                    break
            if theme_part is None:
                continue
            xml = theme_part.blob.decode("utf-8", errors="ignore")
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                continue
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for scheme in root.iter("{%s}clrScheme" % ns["a"]):
                # Count child elements that carry a color (excluding hlink/folHlink for parity with extractor)
                interesting = {"dk1", "lt1", "dk2", "lt2", "accent1", "accent2",
                               "accent3", "accent4", "accent5", "accent6"}
                for child in scheme:
                    tag = child.tag.split("}", 1)[-1]
                    if tag in interesting:
                        out += 1
                if out:
                    return out
    except Exception:
        return out
    return out


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

    # 1. Layout-catalog completeness — use *effective* coverage (direct + fallback)
    # per Microsoft-themes validation finding. A template that maps
    # `claim_with_evidence` cleanly covers `three_pillars`, `metrics`, etc.
    # via the fallback chain even without dedicated layouts.
    n_covered, missing = effective_coverage(layout_map)
    coverage = n_covered / len(LAYOUT_INTENTS)
    sev = _severity_from_fraction(coverage, green_at=0.9, yellow_at=0.6)
    findings.append({
        "criterion": "layout_catalog_completeness",
        "severity": sev,
        "value": f"{len(layout_map)} direct / {n_covered} effective of {len(LAYOUT_INTENTS)}",
        "message": (
            f"{len(layout_map)} of {len(LAYOUT_INTENTS)} IR intents have a direct "
            f"layout match; {n_covered} are covered when fallback chain is "
            f"considered."
        ),
        "remediation": (
            f"Add layouts for: {', '.join(missing)}. Or set `layout_map` "
            f"overrides in profile.yaml to point existing layouts at these intents. "
            f"Note: missing intents may still render acceptably through fallbacks; "
            f"this criterion flags only intents with NO viable path."
        ) if missing else None,
    })

    # 2. Style hierarchy — distinct font sizes OR theme-defined font scheme.
    # Microsoft-themes finding: theme1.xml's fontScheme defines the
    # major/minor tiers; the validator now credits that path.
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

    # Check for theme fontScheme (yields effective hierarchy)
    has_theme_fonts = _has_theme_fontscheme(prs)
    effective_levels = max(n_size_levels, 5 if has_theme_fonts else 0)
    sev = _severity_from_count(effective_levels, green_at=4, yellow_at=2)
    findings.append({
        "criterion": "style_hierarchy",
        "severity": sev,
        "value": f"{n_size_levels} master-defined / {effective_levels} effective",
        "message": (
            f"{n_size_levels} distinct font sizes in slide master(s); "
            f"theme fontScheme present: {has_theme_fonts}. Effective tiers: "
            f"{effective_levels}."
        ),
        "remediation": (
            "Define explicit font-size tokens for heading, body, and caption "
            "tiers in the slide master, or rely on the theme's fontScheme "
            "(majorFont + minorFont). Industry-standard templates take the "
            "theme path."
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

    # 4. Color tokens — count master srgbClr OR theme clrScheme tokens.
    # Microsoft-themes finding: theme1.xml's clrScheme is the canonical home
    # for color tokens in industry templates.
    colors: Counter[str] = Counter()
    for master in prs.slide_masters:
        for el in master.element.iter():
            tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
            if tag == "srgbClr":
                val = el.get("val")
                if val and len(val) == 6:
                    colors[f"#{val.upper()}"] += 1
    n_master_colors = len(colors)
    n_theme_colors = _count_theme_colors(prs)
    n_effective = max(n_master_colors, n_theme_colors)
    sev = _severity_from_count(n_effective, green_at=4, yellow_at=2)
    findings.append({
        "criterion": "color_tokens",
        "severity": sev,
        "value": f"{n_master_colors} master / {n_theme_colors} theme = {n_effective} effective",
        "message": (
            f"{n_master_colors} explicit master colors + {n_theme_colors} theme "
            f"colors = {n_effective} effective tokens. (Templates that use a "
            f"theme typically score on the theme path.)"
        ),
        "remediation": (
            "Define brand colors as tokens. Office templates use theme1.xml's "
            "clrScheme; Figma uses Styles → Colors."
        ) if sev == "red" else None,
    })

    # 5. Type tokens — count master typefaces OR theme fontScheme typefaces.
    # Microsoft-themes finding: theme fontScheme is the canonical home.
    n_typefaces = len(fonts)
    has_theme_fonts = _has_theme_fontscheme(prs)
    # If the theme has a fontScheme, count it as 2 named typefaces
    # (majorFont + minorFont) — that's what well-designed templates use.
    effective_typefaces = max(n_typefaces, 2 if has_theme_fonts else 0)
    if effective_typefaces in (1, 2):
        sev = "green"
    elif effective_typefaces == 0:
        sev = "yellow"
    else:  # >3
        sev = "yellow"
    findings.append({
        "criterion": "type_tokens",
        "severity": sev,
        "value": f"{n_typefaces} master / {effective_typefaces} effective",
        "message": (
            f"{n_typefaces} master typefaces + theme fontScheme present: "
            f"{has_theme_fonts}. Effective typefaces: {effective_typefaces}."
        ),
        "remediation": (
            "Pick 1-2 typefaces (display + body) via the theme's fontScheme "
            "or master rPr. >3 typefaces creates visual noise."
        ) if sev == "yellow" else None,
    })

    # 6. Orphan layouts — "useful extras" vs. "true junk".
    # Microsoft-themes finding: layouts like "Two Content", "Title Only",
    # "Picture with Caption" are legitimate Office structural layouts that
    # don't match our narrative intent names. They're NOT orphans — they're
    # just specialized layouts our IR catalog doesn't try to claim.
    # A true orphan: a layout that no slide uses AND has no placeholders.
    unused_layouts = [name for name in layout_names if name not in layout_map.values()]
    # Per random-PowerPoints finding: rich-catalog templates (e.g.
    # `serving-students` with 60 specialized layouts) can have 90%+ unmapped
    # without being broken. Relax threshold to "extremely high fragmentation
    # only" — true junk is 95%+ unmapped, otherwise extras are fine.
    unused_frac = len(unused_layouts) / len(layout_names) if layout_names else 0.0
    if unused_frac < 0.85:
        sev = "green"
    elif unused_frac < 0.95:
        sev = "yellow"
    else:
        sev = "red"
    findings.append({
        "criterion": "orphan_elements",
        "severity": sev,
        "value": f"{len(unused_layouts)} unmapped of {len(layout_names)}",
        "message": (
            f"{len(unused_layouts)} layout(s) don't map to a narrative IR intent: "
            f"{', '.join(unused_layouts[:5])}"
            + ("..." if len(unused_layouts) > 5 else "") + ". "
            f"These are typically useful Office structural layouts (Two Content, "
            f"Title Only, etc.) and aren't a problem unless catalog is fragmented."
        ),
        "remediation": (
            "Catalog is heavily fragmented. Consider consolidating layouts or "
            "removing unused ones. Most useful layouts (Two Content, etc.) are "
            "expected to be 'unmapped' here without being a problem."
        ) if sev == "red" else None,
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
