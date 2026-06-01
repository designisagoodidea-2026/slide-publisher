"""
template_extractor_figma.py — normalize Figma MCP output into a slide-publisher
template profile entry.

Unlike the pptx extractor, which can call python-pptx directly, the Figma
extractor depends on live MCP access at the *invocation* layer (the skill).
This adapter is the *post-processing* layer: it takes the raw JSON the Figma
MCP returns (slide-template frames, color styles, text styles) and normalizes
it into the slide-publisher template-profile shape.

The skill SKILL.md describes how to drive the Figma MCP to produce the input
JSON, following the 8 Plugin API rules from cos-figma-publish-chain (no
findAll, identify by title text, shallow paths, pre-load fonts, etc.).

Input JSON shape:
    {
        "file_key": "...",
        "slide_templates": [
            {"node_id": "1:1234", "title_text": "Title Slide"},
            {"node_id": "1:1238", "title_text": "Section Header"},
            ...
        ],
        "color_styles": [
            {"name": "Brand/Primary", "hex": "#1F2A44"},
            ...
        ],
        "text_styles": [
            {"name": "Display/L", "family": "Söhne", "size_pt": 48, "weight": 700},
            ...
        ]
    }

Output:
    A template-profile entry suitable for the `templates.figma` branch
    plus a `style_tokens` populates the profile root. See
    template-profile/schema.json for the authoritative shape.

Anonymity: ships in the public plugin. No hard-coded organization patterns.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# IR layout intents (v0.1) — keep in sync with ir/schema.json.
LAYOUT_INTENTS: list[str] = [
    "title", "section_break", "claim_with_evidence", "three_pillars",
    "comparison", "quote", "image_with_caption", "metrics", "timeline", "callout",
]

# Same heuristic patterns the pptx extractor + validator use. Reused here for
# title-text matching (cos-figma-publish-chain Rule 2: identify by title text).
INTENT_PATTERNS: dict[str, list[str]] = {
    "title": ["title slide", "title", "cover", "opening"],
    "section_break": ["section header", "section", "divider", "chapter", "break"],
    "claim_with_evidence": ["title and content", "content", "body", "claim", "supporting"],
    "three_pillars": ["three column", "3 column", "three", "pillars", "tri"],
    "comparison": ["comparison", "compare", "two column", "2 column", "side by side"],
    "quote": ["pull quote", "quote", "blockquote", "testimonial"],
    "image_with_caption": ["image and caption", "picture and caption", "image", "picture", "photo"],
    "metrics": ["stat", "metric", "kpi", "number block", "data"],
    "timeline": ["timeline", "chronology", "milestone", "roadmap"],
    "callout": ["callout", "big statement", "headline", "punchline", "lockup"],
}

# Default semantic names for color and type tokens. Same conventions as pptx
# extractor for cross-format consistency.
COLOR_TOKEN_ROLES: list[str] = [
    "primary", "secondary", "accent", "text-primary", "text-secondary",
    "surface", "surface-muted", "accent-warn",
]
TYPE_TOKEN_ROLES: list[str] = [
    "display", "heading-1", "heading-2", "body", "caption",
]


def map_templates_to_intents(slide_templates: list[dict]) -> dict[str, str]:
    """Map IR layout_intent → Figma node_id based on title_text match.

    First match wins; each node_id is used at most once. Mirrors the pptx
    extractor's pattern-dictionary approach for cross-format consistency.
    """
    mapping: dict[str, str] = {}
    used_ids: set[str] = set()
    for intent in LAYOUT_INTENTS:
        for pattern in INTENT_PATTERNS[intent]:
            for tpl in slide_templates:
                node_id = tpl.get("node_id", "")
                title = tpl.get("title_text", "")
                if not node_id or node_id in used_ids:
                    continue
                if pattern.lower() in title.lower():
                    mapping[intent] = node_id
                    used_ids.add(node_id)
                    break
            if intent in mapping:
                break
    return mapping


def normalize_color_tokens(color_styles: list[dict]) -> dict[str, str]:
    """Map Figma color styles to slide-publisher color tokens.

    Strategy: keep the user's Figma style names (after normalization) when
    they're stable, fall back to semantic roles for the first N styles when
    the user's naming doesn't carry semantic load (e.g., "Color/1", "Color/2").

    For v0.1 simplicity, we always use the Figma style name (kebab-cased).
    Users with semantically-named styles (e.g., "Brand/Primary",
    "Text/Subtle") get an immediately useful token map.
    """
    tokens: dict[str, str] = {}
    for style in color_styles:
        raw_name = style.get("name", "")
        hex_val = style.get("hex", "")
        if not raw_name or not hex_val:
            continue
        # Normalize "Brand/Primary" → "brand-primary"
        token = raw_name.lower().replace("/", "-").replace(" ", "-")
        # Validate hex format
        if not (hex_val.startswith("#") and len(hex_val) in (4, 7, 9)):
            continue
        tokens[token] = hex_val.upper()
    return tokens


def normalize_text_styles(text_styles: list[dict]) -> dict[str, dict[str, Any]]:
    """Map Figma text styles to slide-publisher typography tokens.

    Same strategy as color tokens: kebab-case the Figma style name.
    """
    tokens: dict[str, dict[str, Any]] = {}
    for style in text_styles:
        raw_name = style.get("name", "")
        family = style.get("family", "")
        size_pt = style.get("size_pt")
        weight = style.get("weight", 400)
        if not raw_name or not family or size_pt is None:
            continue
        token = raw_name.lower().replace("/", "-").replace(" ", "-")
        entry: dict[str, Any] = {
            "family": family,
            "size_pt": float(size_pt),
            "weight": int(weight),
        }
        if "line_height" in style:
            entry["line_height"] = float(style["line_height"])
        tokens[token] = entry
    return tokens


def compute_quality_score(
    layout_map: dict[str, str],
    n_templates_inspected: int,
    color_tokens: dict[str, str],
    type_tokens: dict[str, Any],
) -> int:
    """Same weighted heuristic as the pptx extractor."""
    layout_coverage = len(layout_map) / len(LAYOUT_INTENTS)
    layout_breadth = min(1.0, n_templates_inspected / 10.0)
    color_completeness = min(1.0, len(color_tokens) / len(COLOR_TOKEN_ROLES))
    type_completeness = min(1.0, len(type_tokens) / len(TYPE_TOKEN_ROLES))
    score = (
        0.50 * layout_coverage
        + 0.20 * layout_breadth
        + 0.15 * color_completeness
        + 0.15 * type_completeness
    )
    return int(round(score * 100))


def diagnose(
    layout_map: dict[str, str],
    n_templates: int,
    color_tokens: dict[str, str],
    type_tokens: dict,
) -> list[str]:
    findings: list[str] = []
    if n_templates == 0:
        findings.append("No slide-template frames found in the Figma file. "
                        "Make sure each template frame's Heading child contains "
                        "the layout intent as text.")
    missing = [i for i in LAYOUT_INTENTS if i not in layout_map]
    if missing:
        findings.append(
            f"{len(missing)} of {len(LAYOUT_INTENTS)} IR layout intents lack a "
            f"matching template: {', '.join(missing)}. Renderers will fall "
            f"back to 'nearest available' and log substitutions in the loss "
            f"manifest."
        )
    if not color_tokens:
        findings.append(
            "No Figma color styles found. Define styles via Figma → Styles → "
            "Colors so the renderers can theme consistently."
        )
    if not type_tokens:
        findings.append(
            "No Figma text styles found. Define styles via Figma → Styles → "
            "Text so the renderers can match IR layout intents to type tiers."
        )
    if n_templates > 0 and len(layout_map) == len(LAYOUT_INTENTS):
        findings.append("All 10 IR layout intents have a matching Figma slide template.")
    return findings


def extract_from_mcp_output(mcp_output: dict) -> dict[str, Any]:
    """Take the Figma-MCP-shaped JSON and produce a template profile entry."""
    file_key = mcp_output.get("file_key", "")
    slide_templates = mcp_output.get("slide_templates", [])
    color_styles = mcp_output.get("color_styles", [])
    text_styles = mcp_output.get("text_styles", [])

    layout_map = map_templates_to_intents(slide_templates)
    color_tokens = normalize_color_tokens(color_styles)
    type_tokens = normalize_text_styles(text_styles)
    quality_score = compute_quality_score(
        layout_map, len(slide_templates), color_tokens, type_tokens
    )

    # Recommended sidecar path. Renderers will use this on first run.
    template_map_json = (
        f"~/.cowork/plugins/slide-publisher/figma-{file_key}/template-map.json"
    )

    return {
        "file_key": file_key,
        "layout_map": layout_map,
        "template_map_json": template_map_json,
        "quality_score": quality_score,
        "style_tokens": {
            "colors": color_tokens,
            "typography": type_tokens,
        },
        "_inspected_templates": [
            {"node_id": t.get("node_id"), "title_text": t.get("title_text")}
            for t in slide_templates
        ],
        "_findings": diagnose(layout_map, len(slide_templates), color_tokens, type_tokens),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Figma MCP output into a slide-publisher template profile "
            "entry. Input: JSON file (or stdin) with slide_templates, "
            "color_styles, text_styles. Output: profile entry JSON."
        )
    )
    parser.add_argument(
        "input", nargs="?", default="-",
        help="Path to MCP output JSON (default: stdin)",
    )
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    parser.add_argument(
        "--strip-debug", action="store_true",
        help="Omit _inspected_templates and _findings from output",
    )
    args = parser.parse_args()

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.input).read_text()

    try:
        mcp_output = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR parsing input JSON: {e}", file=sys.stderr)
        return 2

    result = extract_from_mcp_output(mcp_output)

    if args.strip_debug:
        result.pop("_inspected_templates", None)
        result.pop("_findings", None)

    out_text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
