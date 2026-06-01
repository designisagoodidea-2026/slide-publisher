"""
remediation_apply_figma.py — automated remediation plan for a Figma file
that failed the validator.

Unlike the pptx remediator (which directly writes the .pptx), the Figma
remediator emits an **MCP creation plan** that the skill's Stage 2 executes
via the Figma MCP. This adapter is the pure-Python middle step.

Input:
    figma_walk_json: output of the Figma MCP walk recipe (file_key, slides,
                     existing_styles) — same shape template-synthesizer-figma
                     consumes.
    validator_path:  path to validator JSON output (from template-validator
                     run with --format figma --profile-entry ...).

Output:
    {
        "file_key": "...",
        "pre_verdict": "fail",
        "fixes_to_apply": [
            {
                "fix_type": "create_color_style",
                "target": "styles.color.<name>",
                "before": null,
                "after": {"name": "primary", "hex": "#1F2A44"},
                "rationale": "Validator flagged color_tokens. No named color styles in the file.",
                "severity_addressed": "color_tokens"
            },
            {
                "fix_type": "create_text_style",
                ...
            },
            {
                "fix_type": "rename_slide_template",
                ...
            },
            ...
        ],
        "deferred": ["..."],
        "stage_2_recipe": "described in skills/remediation-apply-figma/SKILL.md"
    }

The SKILL.md walks through how to execute the plan via the Figma MCP
(applying each fix in turn, then re-running the validator).

Anonymity: ships in the public plugin. No organization patterns.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    LAYOUT_INTENTS, INTENT_TO_HEURISTIC_NAME, DEFAULT_PALETTE, DEFAULT_TYPEFACE,
)

# Default Figma styles. Derived from the shared DEFAULT_PALETTE/DEFAULT_TYPEFACE
# but reshaped into Figma's "Brand/Primary"-style naming convention.
DEFAULT_COLOR_STYLES: list[dict[str, str]] = [
    {"name": f"Brand/{role.title().replace('-', ' ')}", "hex": hex_val}
    for role, hex_val in DEFAULT_PALETTE.items() if "text" not in role and "surface" not in role
] + [
    {"name": "Text/Primary", "hex": DEFAULT_PALETTE["text-primary"]},
    {"name": "Text/Secondary", "hex": DEFAULT_PALETTE["text-secondary"]},
    {"name": "Surface/Default", "hex": DEFAULT_PALETTE["surface"]},
    {"name": "Surface/Muted", "hex": DEFAULT_PALETTE["surface-muted"]},
]

DEFAULT_TEXT_STYLES: list[dict[str, Any]] = [
    {"name": "Display/L", "family": DEFAULT_TYPEFACE, "size_pt": 48, "weight": 700},
    {"name": "Heading/1", "family": DEFAULT_TYPEFACE, "size_pt": 32, "weight": 700},
    {"name": "Heading/2", "family": DEFAULT_TYPEFACE, "size_pt": 24, "weight": 600},
    {"name": "Body/Regular", "family": DEFAULT_TYPEFACE, "size_pt": 18, "weight": 400},
    {"name": "Caption", "family": DEFAULT_TYPEFACE, "size_pt": 12, "weight": 400},
]


def plan(walk: dict[str, Any], validator: dict[str, Any]) -> dict[str, Any]:
    file_key = walk.get("file_key", "")
    existing_styles = walk.get("existing_styles", {}) or {}
    existing_colors = existing_styles.get("colors") or []
    existing_text = existing_styles.get("text") or []
    slide_templates = walk.get("slides", []) or []

    findings = {f["criterion"]: f for f in validator.get("findings", [])}

    fixes: list[dict[str, Any]] = []
    deferred: list[str] = []

    # Fix 1: color_tokens — create named color styles if missing
    color_finding = findings.get("color_tokens", {})
    if color_finding.get("severity") in {"yellow", "red"} and len(existing_colors) < 4:
        for style in DEFAULT_COLOR_STYLES:
            if any(c.get("name") == style["name"] for c in existing_colors):
                continue
            fixes.append({
                "fix_type": "create_color_style",
                "target": f"styles.color.{style['name']}",
                "before": None,
                "after": style,
                "rationale": (
                    "Validator flagged color_tokens; <4 named color styles in "
                    "the file. Adding a default brand-shaped palette."
                ),
                "severity_addressed": "color_tokens",
            })

    # Fix 2: type_tokens — create named text styles if missing
    type_finding = findings.get("type_tokens", {})
    if type_finding.get("severity") in {"yellow", "red"} and len(existing_text) < 3:
        for style in DEFAULT_TEXT_STYLES:
            if any(t.get("name") == style["name"] for t in existing_text):
                continue
            fixes.append({
                "fix_type": "create_text_style",
                "target": f"styles.text.{style['name']}",
                "before": None,
                "after": style,
                "rationale": (
                    "Validator flagged type_tokens; <3 named text styles in "
                    "the file. Adding a default display/heading/body tier."
                ),
                "severity_addressed": "type_tokens",
            })

    # Fix 3: layout_catalog_completeness — rename template frames
    layout_finding = findings.get("layout_catalog_completeness", {})
    if layout_finding.get("severity") in {"yellow", "red"}:
        # Compare what's in the walk against what the IR catalog expects
        existing_names = [t.get("title_text", "").strip() for t in slide_templates]
        matched: set[str] = set()
        # Detect already-matching names
        for intent in LAYOUT_INTENTS:
            for name in existing_names:
                if intent.replace("_", " ") in name.lower() or \
                   INTENT_TO_HEURISTIC_NAME[intent].lower() == name.lower():
                    matched.add(intent)
                    break
        unmapped = [i for i in LAYOUT_INTENTS if i not in matched]

        # Rename unnamed-or-generic templates to the heuristic name for each
        # missing intent. The Figma MCP recipe in the SKILL.md identifies
        # rename targets by node_id.
        generic_targets = [
            t for t in slide_templates
            if not t.get("title_text") or len(t.get("title_text", "")) < 4
        ]
        for intent, target in zip(unmapped, generic_targets):
            fixes.append({
                "fix_type": "rename_slide_template",
                "target": f"node:{target.get('node_id', '?')}",
                "before": target.get("title_text", "(empty)"),
                "after": INTENT_TO_HEURISTIC_NAME[intent],
                "rationale": (
                    f"Validator flagged layout_catalog_completeness; intent "
                    f"'{intent}' had no matching template. Renaming a "
                    "generically-named template to align with IR catalog."
                ),
                "severity_addressed": "layout_catalog_completeness",
            })

    # Fix 4: live_structural_checks — informational, defer
    if findings.get("live_structural_checks"):
        deferred.append(
            "live_structural_checks: deferred to v0.2 (style_hierarchy, "
            "master_usage equivalent, orphan_elements for Figma)."
        )

    return {
        "file_key": file_key,
        "planned_at": dt.datetime.now().isoformat(timespec="seconds"),
        "pre_verdict": validator.get("verdict", "(unknown)"),
        "fixes_to_apply": fixes,
        "deferred": deferred,
        "summary": {
            "total_fixes": len(fixes),
            "by_type": _by_type(fixes),
        },
        "stage_2_recipe_ref": "skills/remediation-apply-figma/SKILL.md",
    }


def _by_type(fixes: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in fixes:
        out[f["fix_type"]] = out.get(f["fix_type"], 0) + 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plan automated Figma remediation. Input: walk JSON (from MCP) "
            "+ validator JSON. Output: a fix plan + Stage 2 recipe reference."
        )
    )
    parser.add_argument("walk", help="Path to figma walk JSON")
    parser.add_argument("--validator-report", required=True,
                        help="Path to validator JSON output")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    walk_path = Path(args.walk).expanduser()
    validator_path = Path(args.validator_report).expanduser()
    if not walk_path.exists():
        print(f"ERROR: {walk_path} not found.", file=sys.stderr)
        return 2
    if not validator_path.exists():
        print(f"ERROR: {validator_path} not found.", file=sys.stderr)
        return 2

    walk = json.loads(walk_path.read_text())
    validator = json.loads(validator_path.read_text())

    try:
        result = plan(walk, validator)
    except Exception as e:
        print(f"ERROR planning: {e}", file=sys.stderr)
        return 1

    out_text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).expanduser().write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
