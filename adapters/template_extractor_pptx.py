"""
template_extractor_pptx.py — extract a slide-publisher template profile from a loose .pptx.

Inputs:
    pptx_path: path to a .pptx file (existing template OR a deck that follows
               an implicit visual identity but isn't structured as a template).

Outputs:
    A dict with shape:
        {
            "layout_map": {<IR layout_intent>: <pptx layout name>, ...},
            "style_tokens": {
                "colors": {<token name>: "#RRGGBB", ...},
                "typography": {<role>: {family, size_pt, weight}, ...},
            },
            "quality_score": <int 0-100>,
            "_inspected_layouts": [<pptx layout name>, ...],
            "_findings": [<human-readable observation>, ...],
        }

    "layout_map" and "quality_score" populate the template-profile schema's
    `templates.pptx` branch. "style_tokens" populates the schema's top-level
    `style_tokens`. `_inspected_layouts` and `_findings` are debug-only — strip
    them before persisting the profile.

This adapter is heuristic. It infers layout intent from layout names using a
small pattern dictionary, and color/typography tokens from the slide master's
XML (python-pptx doesn't expose theme tokens directly). The output is a
*candidate* template profile that the user reviews before locking in.

Anonymity: this adapter ships in the public plugin. It hard-codes no user data,
no organization-specific patterns, no proprietary mappings. Pattern dictionary
is generic.
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
    LAYOUT_INTENTS, INTENT_PATTERNS, COLOR_TOKEN_ROLES, TYPE_TOKEN_ROLES,
    infer_layout_map, quality_score,
)

try:
    from pptx import Presentation
except ImportError:
    print(
        "ERROR: python-pptx is not installed. Install with:\n"
        "    pip install python-pptx",
        file=sys.stderr,
    )
    sys.exit(2)


def collect_layouts(prs: "Presentation") -> list[tuple[int, int, str]]:
    """Return all layouts across all masters as (master_idx, layout_idx, name)."""
    out = []
    for mi, master in enumerate(prs.slide_masters):
        for li, layout in enumerate(master.slide_layouts):
            out.append((mi, li, layout.name))
    return out


def _infer_from_tuples(layouts: list[tuple[int, int, str]]) -> dict[str, str]:
    """Adapter to use the shared infer_layout_map with this file's tuple type."""
    return infer_layout_map([name for _, _, name in layouts])


def extract_color_tokens(prs: "Presentation") -> dict[str, str]:
    """Collect color tokens. Prefer theme1.xml clrScheme; fall back to master srgbClr.

    Microsoft-themes finding: industry-standard templates carry colors in
    `ppt/theme/theme1.xml`'s <a:clrScheme>, not as <a:srgbClr> in slideMaster.
    Reading both gives well-built templates a fair shake.
    """
    # First try the theme scheme (canonical Office templates land here)
    theme_colors = _extract_theme_clrscheme(prs)
    if theme_colors:
        return theme_colors

    # Fallback: walk master XML for srgbClr (historic v0.1 behavior)
    colors: Counter[str] = Counter()
    for master in prs.slide_masters:
        try:
            for el in master.element.iter():
                tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
                if tag == "srgbClr":
                    val = el.get("val")
                    if val and len(val) == 6:
                        colors[f"#{val.upper()}"] += 1
        except Exception:
            continue
    tokens: dict[str, str] = {}
    for role, (hex_val, _count) in zip(COLOR_TOKEN_ROLES, colors.most_common(len(COLOR_TOKEN_ROLES))):
        tokens[role] = hex_val
    return tokens


# Map clrScheme element names to our COLOR_TOKEN_ROLES.
_CLRSCHEME_TO_ROLE: dict[str, str] = {
    "dk1": "text-primary",
    "lt1": "surface",
    "dk2": "text-secondary",
    "lt2": "surface-muted",
    "accent1": "primary",
    "accent2": "secondary",
    "accent3": "accent",
    "accent4": "accent-warn",
}


def _extract_theme_clrscheme(prs: "Presentation") -> dict[str, str]:
    """Read theme1.xml's clrScheme. Returns role → "#RRGGBB"."""
    out: dict[str, str] = {}
    try:
        # The theme XML is attached as a part to the slide master.
        for master in prs.slide_masters:
            theme_part = None
            try:
                # Walk master's part relationships for the theme part
                for rel_id, rel in master.part.rels.items():
                    if rel.reltype.endswith("/theme"):
                        theme_part = rel.target_part
                        break
            except Exception:
                pass
            if theme_part is None:
                continue
            try:
                theme_xml = theme_part.blob.decode("utf-8", errors="ignore")
            except Exception:
                continue
            # Parse the clrScheme
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(theme_xml)
            except ET.ParseError:
                continue
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for scheme in root.iter("{%s}clrScheme" % ns["a"]):
                for child in scheme:
                    tag = child.tag.split("}", 1)[-1] if "}" in child.tag else child.tag
                    role = _CLRSCHEME_TO_ROLE.get(tag)
                    if role is None:
                        continue
                    # Color may be srgbClr or sysClr (the latter has lastClr fallback)
                    color_el = (
                        child.find("a:srgbClr", ns)
                        or child.find("a:sysClr", ns)
                    )
                    if color_el is None:
                        continue
                    # sysClr exposes a `lastClr` resolved hex; srgbClr exposes `val`.
                    # Prefer the resolved hex for sysClr; fall back to `val` for srgbClr.
                    val = color_el.get("lastClr") or color_el.get("val")
                    if val and len(val) == 6 and all(c in "0123456789abcdefABCDEF" for c in val):
                        out[role] = f"#{val.upper()}"
            if out:
                return out  # Found scheme on first master with one
    except Exception:
        return out
    return out


def extract_typography(prs: "Presentation") -> dict[str, dict[str, Any]]:
    """Collect typography tokens. Prefer theme1.xml fontScheme; fall back to master.

    Microsoft-themes finding: industry templates declare typography via
    theme1.xml's fontScheme (majorFont/minorFont), not as inline <a:rPr>
    sizes on the master. Read the scheme first.
    """
    # First try the theme scheme — yields a 2-tier display/body model
    scheme = _extract_theme_fontscheme(prs)
    if scheme:
        major = scheme.get("major", "Calibri Light")
        minor = scheme.get("minor", "Calibri")
        return {
            "display": {"family": major, "size_pt": 40.0, "weight": 700},
            "heading-1": {"family": major, "size_pt": 28.0, "weight": 700},
            "heading-2": {"family": major, "size_pt": 22.0, "weight": 600},
            "body": {"family": minor, "size_pt": 18.0, "weight": 400},
            "caption": {"family": minor, "size_pt": 12.0, "weight": 400},
        }

    # Fallback: master XML inspection (historic v0.1 behavior)
    fonts: Counter[str] = Counter()
    sizes: Counter[int] = Counter()
    for master in prs.slide_masters:
        try:
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
        except Exception:
            continue

    primary_family = fonts.most_common(1)[0][0] if fonts else "Calibri"
    distinct_sizes = sorted({s for s, _ in sizes.most_common(20) if s > 0}, reverse=True)

    typography: dict[str, dict[str, Any]] = {}
    for i, role in enumerate(TYPE_TOKEN_ROLES):
        if i >= len(distinct_sizes):
            break
        typography[role] = {
            "family": primary_family,
            "size_pt": float(distinct_sizes[i]),
            "weight": 700 if i < 2 else 400,
        }
    return typography


def _extract_theme_fontscheme(prs: "Presentation") -> dict[str, str]:
    """Read theme1.xml's fontScheme. Returns {major, minor} typeface names."""
    out: dict[str, str] = {}
    try:
        for master in prs.slide_masters:
            theme_part = None
            try:
                for rel_id, rel in master.part.rels.items():
                    if rel.reltype.endswith("/theme"):
                        theme_part = rel.target_part
                        break
            except Exception:
                continue
            if theme_part is None:
                continue
            try:
                theme_xml = theme_part.blob.decode("utf-8", errors="ignore")
            except Exception:
                continue
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(theme_xml)
            except ET.ParseError:
                continue
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for tier in ("major", "minor"):
                font_el = root.find(f".//a:fontScheme/a:{tier}Font/a:latin", ns)
                if font_el is not None:
                    tf = font_el.get("typeface")
                    if tf:
                        out[tier] = tf
            if out:
                return out
    except Exception:
        return out
    return out


def compute_quality_score(
    layout_map: dict[str, str],
    layouts: list[tuple[int, int, str]],
    color_tokens: dict[str, str],
    type_tokens: dict[str, dict[str, Any]],
) -> int:
    """Same as _common.quality_score but with this file's calling shape."""
    return quality_score(
        layout_map=layout_map,
        n_layouts=len(layouts),
        n_color_tokens=len(color_tokens),
        n_type_tokens=len(type_tokens),
    )


def diagnose(
    layout_map: dict[str, str],
    layouts: list[tuple[int, int, str]],
    color_tokens: dict[str, str],
    type_tokens: dict[str, dict[str, Any]],
) -> list[str]:
    """Human-readable observations about template completeness."""
    findings: list[str] = []
    if len(layouts) == 0:
        findings.append("No slide layouts found. Is this a valid .pptx?")
    elif len(layouts) < 5:
        findings.append(
            f"Only {len(layouts)} layouts found. Templates typically have 8-12; "
            "consider extending the catalog."
        )
    missing = [i for i in LAYOUT_INTENTS if i not in layout_map]
    if missing:
        findings.append(
            f"{len(missing)} of 10 IR layout intents have no matching pptx "
            f"layout: {', '.join(missing)}. Renderers will fall back to "
            "'nearest available' and log a substitution in the loss manifest."
        )
    if len(color_tokens) == 0:
        findings.append(
            "No explicit color tokens extracted. The template may rely on theme "
            "colors only; renderers will inherit from the slide master."
        )
    if len(type_tokens) == 0:
        findings.append(
            "No typography tokens extracted. The template may not define explicit "
            "type styles in its masters."
        )
    if len(layouts) > 0 and len(layout_map) == len(LAYOUT_INTENTS):
        findings.append(
            "All 10 IR layout intents have a matching pptx layout. Clean coverage."
        )
    return findings


def extract(pptx_path: str | Path) -> dict[str, Any]:
    """Run the full extraction pipeline against a .pptx file."""
    prs = Presentation(str(pptx_path))
    layouts = collect_layouts(prs)
    layout_map = _infer_from_tuples(layouts)
    color_tokens = extract_color_tokens(prs)
    type_tokens = extract_typography(prs)
    quality_score = compute_quality_score(layout_map, layouts, color_tokens, type_tokens)
    findings = diagnose(layout_map, layouts, color_tokens, type_tokens)
    return {
        "layout_map": layout_map,
        "style_tokens": {
            "colors": color_tokens,
            "typography": type_tokens,
        },
        "quality_score": quality_score,
        "_inspected_layouts": [name for _, _, name in layouts],
        "_findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a slide-publisher template profile from a loose .pptx. "
            "Emits JSON to stdout (or --out path) with layout_map, style_tokens, "
            "quality_score, and human-readable findings."
        )
    )
    parser.add_argument("pptx", help="Path to .pptx template or loose deck")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    parser.add_argument(
        "--strip-debug",
        action="store_true",
        help="Omit _inspected_layouts and _findings from output",
    )
    args = parser.parse_args()

    pptx_path = Path(args.pptx).expanduser()
    if not pptx_path.exists():
        print(f"ERROR: {pptx_path} not found.", file=sys.stderr)
        return 2
    if pptx_path.suffix.lower() != ".pptx":
        print(
            f"WARNING: {pptx_path} doesn't have a .pptx extension; attempting "
            "extraction anyway.",
            file=sys.stderr,
        )

    try:
        result = extract(pptx_path)
    except Exception as e:
        print(f"ERROR extracting template: {e}", file=sys.stderr)
        return 1

    if args.strip_debug:
        result.pop("_inspected_layouts", None)
        result.pop("_findings", None)

    out_text = json.dumps(result, indent=2, sort_keys=False)
    if args.out:
        Path(args.out).expanduser().write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
