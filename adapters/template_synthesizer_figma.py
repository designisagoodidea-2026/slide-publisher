"""
template_synthesizer_figma.py — synthesize a Figma template from MCP-gathered
slide-walk data.

Unlike the pptx synthesizer, this adapter does not directly write Figma files.
The Figma MCP runtime is required to (a) walk the source slides to produce
the input JSON, and (b) create the synthesized template frames in the user's
file. This adapter does the algorithmic middle step — clustering and pattern
derivation.

Input JSON shape (produced by the SKILL.md's MCP recipe):
    {
        "file_key": "...",
        "slides": [
            {
                "slide_id": "1:100",
                "shapes": [
                    {
                        "kind": "text" | "image" | "frame" | "rect",
                        "x": <pixels>, "y": <pixels>,
                        "width": <pixels>, "height": <pixels>,
                        "text": "...",
                        "font_family": "Söhne",
                        "font_size_pt": 48,
                        "font_weight": 700,
                        "fill_hex": "#1F2A44"
                    },
                    ...
                ]
            },
            ...
        ],
        "existing_styles": {
            "colors": [{"name": "...", "hex": "#..."}, ...],
            "text": [{"name": "...", "family": "...", "size_pt": ..., "weight": ...}, ...]
        }
    }

Output JSON shape:
    {
        "file_key": "...",
        "n_slides": int,
        "n_clusters": int,
        "clusters": [
            {
                "cluster_id": int,
                "derived_name": str,
                "suggested_intent": str,
                "member_slide_ids": [str, ...],
                "canonical_shapes": [...]  # pattern the MCP should re-create
            },
            ...
        ],
        "suggested_layout_map": {<intent>: <derived_name>, ...},
        "extracted_tokens": {"colors": {...}, "typography": {...}},
        "mcp_creation_plan": {
            "templates_page_name": "Templates (synthesized by slide-publisher)",
            "frames_to_create": [
                {
                    "name": <derived_name>,
                    "frame_size": {"width": 1920, "height": 1080},
                    "children": [
                        {
                            "type": "TEXT",
                            "x": <px>, "y": <px>,
                            "width": <px>, "height": <px>,
                            "text": "<placeholder>",
                            "font": {...}
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    }

The SKILL.md drives the MCP through both the slide-walk step and the
frame-creation step. This adapter is pure post-processing.

Anonymity: ships in the public plugin. No organization patterns; no defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


from _common import (  # noqa: E402
    POSITION_QUANTUM_PX, FONT_SIZE_QUANTUM_PT as FONT_SIZE_QUANTUM,
    quantize as _q,
)


def profile_shape(shape: dict) -> tuple:
    """Stable, quantized signature for clustering."""
    return (
        shape.get("kind", "other"),
        _q(shape.get("x"), POSITION_QUANTUM_PX),
        _q(shape.get("y"), POSITION_QUANTUM_PX),
        _q(shape.get("width"), POSITION_QUANTUM_PX),
        _q(shape.get("height"), POSITION_QUANTUM_PX),
        _q(shape.get("font_size_pt"), FONT_SIZE_QUANTUM),
    )


def profile_slide(slide: dict) -> tuple[str, tuple]:
    """Return (slide_id, signature) sorted shape tuple."""
    shapes_sorted = sorted(
        slide.get("shapes", []),
        key=lambda s: (s.get("y", 0), s.get("x", 0)),
    )
    sig = tuple(profile_shape(s) for s in shapes_sorted)
    return slide.get("slide_id", ""), sig


def cluster(slides: list[dict]) -> list[dict]:
    """Exact-match cluster on profiled signature."""
    groups: dict[tuple, list[str]] = defaultdict(list)
    canonical: dict[tuple, list[dict]] = {}
    for slide in slides:
        sid, sig = profile_slide(slide)
        groups[sig].append(sid)
        if sig not in canonical:
            # Keep the original shape list (in sorted order) as the canonical
            shapes_sorted = sorted(
                slide.get("shapes", []),
                key=lambda s: (s.get("y", 0), s.get("x", 0)),
            )
            canonical[sig] = shapes_sorted
    out = []
    for cid, (sig, members) in enumerate(groups.items()):
        shapes = canonical[sig]
        name = derive_name(shapes)
        intent = suggest_intent(name, shapes)
        out.append({
            "cluster_id": cid,
            "derived_name": name,
            "suggested_intent": intent,
            "member_slide_ids": members,
            "n_members": len(members),
            "canonical_shapes": shapes,
        })
    return out


def derive_name(shapes: list[dict]) -> str:
    """Heuristic naming — same logic as pptx synthesizer for cross-format parity."""
    text_shapes = [s for s in shapes if s.get("kind") == "text"]
    image_shapes = [s for s in shapes if s.get("kind") == "image"]
    n_text = len(text_shapes)
    n_image = len(image_shapes)

    if not shapes:
        return "Blank"

    sizes = sorted(
        [s.get("font_size_pt", 0) or 0 for s in text_shapes],
        reverse=True,
    )
    largest = sizes[0] if sizes else 0
    second = sizes[1] if len(sizes) > 1 else 0

    # Order matters — check huge-font cases first
    if n_text == 2 and n_image == 0:
        if largest >= 80:
            return "Stat Block"
        if largest >= 40 and second <= 24:
            return "Title Slide"
        if largest >= 24 and second <= 16:
            return "Pull Quote"

    if n_text == 4 and n_image == 0:
        cols = text_shapes[-3:]
        widths = sorted({_q(s.get("width"), POSITION_QUANTUM_PX) for s in cols})
        if len(widths) <= 2:
            return "Three Column"

    if n_text == 1 and n_image == 0:
        return "Section Header"

    if n_image >= 1 and n_text <= 2:
        return "Image and Caption"

    return f"Custom Layout (n_text={n_text}, n_image={n_image})"


def suggest_intent(name: str, shapes: list[dict]) -> str:
    n = name.lower()
    if "title slide" in n:
        return "title"
    if "section" in n:
        return "section_break"
    if "three" in n or "column" in n:
        return "three_pillars"
    if "quote" in n:
        return "quote"
    if "stat" in n or "metric" in n:
        return "metrics"
    if "image" in n or "picture" in n:
        return "image_with_caption"
    if "compar" in n:
        return "comparison"
    if "timeline" in n:
        return "timeline"
    return "claim_with_evidence"


def extract_tokens(slides: list[dict], existing_styles: dict) -> dict[str, Any]:
    """Aggregate tokens. Prefer existing named styles; fall back to slide-derived."""
    colors_out: dict[str, str] = {}
    typography_out: dict[str, dict[str, Any]] = {}

    # Honor named styles if present
    for style in existing_styles.get("colors", []):
        if style.get("name") and style.get("hex"):
            token = style["name"].lower().replace("/", "-").replace(" ", "-")
            colors_out[token] = style["hex"].upper()
    for style in existing_styles.get("text", []):
        if style.get("name"):
            token = style["name"].lower().replace("/", "-").replace(" ", "-")
            typography_out[token] = {
                "family": style.get("family", "Helvetica"),
                "size_pt": float(style.get("size_pt", 16)),
                "weight": int(style.get("weight", 400)),
            }

    # If no named styles, derive from slide content
    if not colors_out:
        fills: Counter[str] = Counter()
        for s in slides:
            for sh in s.get("shapes", []):
                if sh.get("fill_hex"):
                    fills[sh["fill_hex"].upper()] += 1
        for role, (hex_val, _) in zip(
            ["primary", "secondary", "accent", "text-primary",
             "text-secondary", "surface", "surface-muted"],
            fills.most_common(7),
        ):
            colors_out[role] = hex_val

    if not typography_out:
        sizes: Counter[int] = Counter()
        families: Counter[str] = Counter()
        for s in slides:
            for sh in s.get("shapes", []):
                if sh.get("font_size_pt"):
                    sizes[int(sh["font_size_pt"])] += 1
                if sh.get("font_family"):
                    families[sh["font_family"]] += 1
        primary_family = families.most_common(1)[0][0] if families else "Helvetica"
        distinct = sorted({s for s, _ in sizes.most_common(20) if s > 0},
                          reverse=True)
        for i, role in enumerate(["display", "heading-1", "heading-2",
                                  "body", "caption"]):
            if i >= len(distinct):
                break
            typography_out[role] = {
                "family": primary_family,
                "size_pt": float(distinct[i]),
                "weight": 700 if i < 2 else 400,
            }

    return {"colors": colors_out, "typography": typography_out}


def build_creation_plan(clusters: list[dict]) -> dict[str, Any]:
    """Build the MCP-driven frame-creation plan."""
    plan = {
        "templates_page_name": "Templates (synthesized by slide-publisher)",
        "frame_size": {"width": 1920, "height": 1080},
        "frames_to_create": [],
    }
    for c in clusters:
        children = []
        for shape in c["canonical_shapes"]:
            if shape.get("kind") == "text":
                children.append({
                    "type": "TEXT",
                    "x": shape.get("x", 0),
                    "y": shape.get("y", 0),
                    "width": shape.get("width", 200),
                    "height": shape.get("height", 50),
                    "placeholder_text": _placeholder_for_shape(shape),
                    "font": {
                        "family": shape.get("font_family", "Helvetica"),
                        "size_pt": shape.get("font_size_pt", 16),
                        "weight": shape.get("font_weight", 400),
                    },
                    "fill_hex": shape.get("fill_hex", "#000000"),
                })
            elif shape.get("kind") == "image":
                children.append({
                    "type": "RECTANGLE",
                    "x": shape.get("x", 0),
                    "y": shape.get("y", 0),
                    "width": shape.get("width", 400),
                    "height": shape.get("height", 300),
                    "name": "Image placeholder",
                })
        plan["frames_to_create"].append({
            "name": c["derived_name"],
            "intent": c["suggested_intent"],
            "children": children,
        })
    return plan


def _placeholder_for_shape(shape: dict) -> str:
    """Generate a reasonable placeholder text based on shape properties."""
    size = shape.get("font_size_pt", 16)
    if size >= 80:
        return "{{ Big Number }}"
    if size >= 40:
        return "{{ Title }}"
    if size >= 24:
        return "{{ Heading }}"
    return "{{ Body Text }}"


def synthesize(input_json: dict) -> dict[str, Any]:
    slides = input_json.get("slides", [])
    existing_styles = input_json.get("existing_styles", {})
    file_key = input_json.get("file_key", "")

    clusters = cluster(slides)
    tokens = extract_tokens(slides, existing_styles)

    layout_map: dict[str, str] = {}
    for c in clusters:
        intent = c["suggested_intent"]
        if intent not in layout_map:
            layout_map[intent] = c["derived_name"]

    creation_plan = build_creation_plan(clusters)

    return {
        "file_key": file_key,
        "n_slides": len(slides),
        "n_clusters": len(clusters),
        "clusters": clusters,
        "suggested_layout_map": layout_map,
        "extracted_tokens": tokens,
        "mcp_creation_plan": creation_plan,
        "v0_1_caveats": [
            "Stage-2 frame creation in Figma is MCP-driven; this adapter "
            "produces the plan but does not execute it. The SKILL.md walks "
            "through the Plugin API call sequence.",
            "Clustering is exact-match on quantized signature. Slides "
            "with >16px drift in position may not cluster together; v0.2 "
            "will support similarity-thresholded clustering.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Synthesize a Figma template plan from MCP-gathered slide-walk "
            "data. Input: JSON (stdin or file) describing slides; output: "
            "cluster plan + suggested layout_map + tokens + Plugin API "
            "frame-creation plan."
        )
    )
    parser.add_argument("input", nargs="?", default="-",
                        help="Input JSON path (default: stdin)")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.input == "-" else Path(args.input).expanduser().read_text()
    try:
        input_json = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR parsing input: {e}", file=sys.stderr)
        return 2

    try:
        result = synthesize(input_json)
    except Exception as e:
        print(f"ERROR synthesizing: {e}", file=sys.stderr)
        return 1

    out_text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).expanduser().write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
