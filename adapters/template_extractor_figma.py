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

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    LAYOUT_INTENTS, INTENT_PATTERNS, COLOR_TOKEN_ROLES, TYPE_TOKEN_ROLES,
    quality_score, diagnose_coverage,
)


def map_templates_to_intents(slide_templates: list[dict]) -> dict[str, str]:
    """Map IR layout_intent → Figma node_id.

    Two paths:
      1. Direct intent (preferred, 0.2.0-dev+): if a slide template carries an
         `intent` field (set by the MCP probe from shared plugin data
         `slide_publisher.intent` or from an off-canvas INTENT text node),
         use it directly. This is how the starter template and any
         template authored via our setup conventions are extracted.
      2. Pattern match on title_text (legacy, 0.1.x): fall back to the
         INTENT_PATTERNS dict — matches Figma slides whose title text
         resembles an IR intent name. Used for user-supplied Figma decks
         that pre-date the shared-plugin-data convention.
    """
    mapping: dict[str, str] = {}
    used_ids: set[str] = set()
    # Path 1 — direct intent
    for tpl in slide_templates:
        intent = tpl.get("intent")
        node_id = tpl.get("node_id", "")
        if intent and intent in LAYOUT_INTENTS and node_id and node_id not in used_ids:
            mapping[intent] = node_id
            used_ids.add(node_id)
    # Path 2 — pattern fallback for intents not yet mapped
    for intent in LAYOUT_INTENTS:
        if intent in mapping:
            continue
        for pattern in INTENT_PATTERNS[intent]:
            for tpl in slide_templates:
                if tpl.get("intent"):
                    continue  # already handled in path 1
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
    return quality_score(
        layout_map=layout_map,
        n_layouts=n_templates_inspected,
        n_color_tokens=len(color_tokens),
        n_type_tokens=len(type_tokens),
    )


def diagnose(
    layout_map: dict[str, str],
    n_templates: int,
    color_tokens: dict[str, str],
    type_tokens: dict,
) -> list[str]:
    return diagnose_coverage(
        n_layouts_inspected=n_templates,
        layout_map=layout_map,
        n_color_tokens=len(color_tokens),
        n_type_tokens=len(type_tokens),
        format_label="Figma slide template",
    )


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
