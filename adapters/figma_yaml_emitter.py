"""
figma_yaml_emitter.py — translate a Deck IR + template profile into the
per-slide YAML the Figma MCP publishing layer consumes, plus a loss manifest.

Inputs:
    ir_path:      Deck IR YAML
    profile_path: template profile YAML (must have `templates.figma`)
    out_path:    where to write the per-slide YAML

Outputs:
    <out_path>           — per-slide YAML array (consumed by the Figma MCP step)
    <out_path>.loss.md   — markdown loss manifest
    <out_path>.loss.json — JSON sidecar

Unlike pptx_renderer.py, this emitter does not produce the final deck. It
produces an intermediate per-slide YAML that the Figma MCP turns into Figma
slides at the user's runtime. See skills/render-figma/SKILL.md for the
post-emit invocation pattern (the 8 Plugin API rules apply).

Anonymity: ships in the public plugin. No hard-coded layouts, no organization
patterns, no user-specific defaults.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is not installed. Install with: pip install pyyaml",
          file=sys.stderr)
    sys.exit(2)


# Same fallback chain as render-pptx — keeps cross-renderer behavior consistent.
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


# ---- Loss manifest (mirrors pptx_renderer.py) ----------------------------

@dataclass
class LossEntry:
    category: str          # LOSSLESS | LOSSY | DROPPED | ANNOTATED
    slide_id: str | None
    field: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "slide_id": self.slide_id,
            "field": self.field,
            "detail": self.detail,
        }


@dataclass
class LossManifest:
    deck_title: str = ""
    rendered_at: str = ""
    renderer: str = "render-figma"
    file_key: str = ""
    entries: list[LossEntry] = field(default_factory=list)

    def add(self, category: str, slide_id: str | None, field_name: str, detail: str) -> None:
        self.entries.append(LossEntry(category, slide_id, field_name, detail))

    def to_markdown(self) -> str:
        counts = {cat: sum(1 for e in self.entries if e.category == cat)
                  for cat in ["LOSSLESS", "LOSSY", "DROPPED", "ANNOTATED"]}
        lines = [
            f"> Summary: {counts['LOSSLESS']} lossless, {counts['LOSSY']} lossy, "
            f"{counts['DROPPED']} dropped, {counts['ANNOTATED']} annotated.\n",
            f"# Loss manifest — {self.deck_title}",
            "",
            f"- Rendered: {self.rendered_at}",
            f"- Renderer: `{self.renderer}`",
            f"- Figma file: `{self.file_key}`",
            "",
        ]
        for cat in ["LOSSLESS", "LOSSY", "DROPPED", "ANNOTATED"]:
            cat_entries = [e for e in self.entries if e.category == cat]
            if not cat_entries:
                continue
            lines.append(f"## {cat} ({len(cat_entries)})")
            lines.append("")
            for e in cat_entries:
                scope = f"slide `{e.slide_id}`" if e.slide_id else "deck-level"
                lines.append(f"- **{scope} / {e.field}** — {e.detail}")
            lines.append("")
        return "\n".join(lines) + "\n"

    def to_json(self) -> dict:
        counts = {cat.lower(): sum(1 for e in self.entries if e.category == cat)
                  for cat in ["LOSSLESS", "LOSSY", "DROPPED", "ANNOTATED"]}
        return {
            "deck_title": self.deck_title,
            "rendered_at": self.rendered_at,
            "renderer": self.renderer,
            "file_key": self.file_key,
            "summary": counts,
            "entries": [e.to_dict() for e in self.entries],
        }


# ---- Layout resolution ---------------------------------------------------

def resolve_template_node_id(
    layout_map: dict[str, str],
    intent: str,
    manifest: LossManifest,
    slide_id: str,
) -> str | None:
    """Resolve the Figma node_id for a given IR layout intent.

    Returns the node_id of the slide template to clone, or None if no
    suitable template exists.
    """
    node_id = layout_map.get(intent)
    if node_id:
        return node_id

    # Fallback chain
    for alt_intent in LAYOUT_FALLBACKS.get(intent, []):
        alt_id = layout_map.get(alt_intent)
        if alt_id:
            manifest.add(
                "LOSSY", slide_id, "layout_intent",
                f"intent '{intent}' substituted to '{alt_intent}' "
                f"(figma node {alt_id}) via the documented fallback chain.",
            )
            return alt_id

    # Universal default
    default_id = layout_map.get("claim_with_evidence")
    if default_id:
        manifest.add(
            "LOSSY", slide_id, "layout_intent",
            f"intent '{intent}' had no mapping or fallback; defaulted to "
            f"'claim_with_evidence' (figma node {default_id}).",
        )
        return default_id

    manifest.add(
        "DROPPED", slide_id, "layout_intent",
        f"intent '{intent}' had no mapping, no fallback, and no universal "
        f"default. Slide will be skipped by the publisher.",
    )
    return None


# ---- Body block rendering ------------------------------------------------

def render_body_blocks(
    body_blocks: list[dict],
    manifest: LossManifest,
    slide_id: str,
) -> list[dict]:
    """Translate IR body_blocks into the per-block records the Figma MCP
    publisher consumes.

    Each output record has shape:
        {
            "kind": "<one of: prose | bullets | metric | quote | image | diagram>",
            "text": "<string or array of strings>",
            "_position_hint": <int | None>  # which content frame, if known
        }

    Mapping is intentionally simple — the Figma publisher handles font
    styling, placement, and constraint resolution at MCP-time.
    """
    out: list[dict] = []
    for i, block in enumerate(body_blocks):
        kind = block.get("kind", "")
        content = block.get("content")
        if kind == "prose":
            out.append({"kind": "prose", "text": str(content)})
        elif kind == "bullets":
            if isinstance(content, list):
                out.append({"kind": "bullets", "text": list(content)})
        elif kind == "metric":
            if isinstance(content, dict):
                out.append({"kind": "metric", "text": {
                    "label": content.get("label", ""),
                    "value": content.get("value", ""),
                    "unit": content.get("unit", ""),
                    "comparison": content.get("comparison", ""),
                }})
        elif kind == "quote":
            if isinstance(content, dict):
                out.append({"kind": "quote", "text": {
                    "text": content.get("text", ""),
                    "attribution": content.get("attribution", ""),
                }})
        elif kind == "image_placeholder":
            if isinstance(content, dict):
                manifest.add(
                    "ANNOTATED", slide_id,
                    f"body_blocks[{i}].kind=image_placeholder",
                    "image_placeholder emitted as alt+intent caption; no "
                    "image asset is uploaded by this renderer.",
                )
                out.append({"kind": "image_caption", "text": {
                    "alt": content.get("alt", ""),
                    "intent": content.get("intent", ""),
                }})
        elif kind == "diagram_placeholder":
            if isinstance(content, dict):
                manifest.add(
                    "ANNOTATED", slide_id,
                    f"body_blocks[{i}].kind=diagram_placeholder",
                    "diagram_placeholder emitted as alt+intent caption; no "
                    "diagram is constructed by this renderer.",
                )
                out.append({"kind": "diagram_caption", "text": {
                    "alt": content.get("alt", ""),
                    "intent": content.get("intent", ""),
                }})
        else:
            manifest.add(
                "DROPPED", slide_id, f"body_blocks[{i}].kind={kind}",
                f"unknown body_block kind '{kind}'; dropped.",
            )
    return out


# ---- Main translation pipeline -------------------------------------------

def translate(ir_path: Path, profile_path: Path) -> tuple[list[dict], LossManifest]:
    ir = yaml.safe_load(ir_path.read_text())
    profile = yaml.safe_load(profile_path.read_text())

    figma_branch = profile.get("templates", {}).get("figma")
    if not figma_branch:
        raise ValueError("Profile has no `templates.figma` branch. "
                         "render-figma cannot proceed.")
    layout_map = figma_branch.get("layout_map", {})
    file_key = figma_branch.get("file_key", "")

    manifest = LossManifest(
        deck_title=ir.get("deck", {}).get("title", ""),
        rendered_at=dt.datetime.now().isoformat(timespec="seconds"),
        file_key=file_key,
    )

    # Deck-level fields with no native figma representation
    deck = ir.get("deck", {})
    for f in ["audience", "throughline", "arc", "evidence_anchor",
              "duration_min", "voice_constraints"]:
        if deck.get(f):
            manifest.add(
                "DROPPED", None, f"deck.{f}",
                f"'{f}' has no native Figma representation; preserved in the "
                f"loss manifest only (value: {str(deck.get(f))[:80]}).",
            )

    if deck.get("title"):
        manifest.add("LOSSLESS", None, "deck.title",
                     "deck title preserved as the publisher's batch label.")

    slide_records: list[dict] = []
    for slide_def in ir.get("slides", []):
        slide_id = slide_def.get("id", "")
        intent = slide_def.get("layout_intent", "")
        node_id = resolve_template_node_id(layout_map, intent, manifest, slide_id)
        if node_id is None:
            continue  # skipped — already recorded as DROPPED

        body = render_body_blocks(slide_def.get("body_blocks", []), manifest, slide_id)

        record = {
            "slide_id": slide_id,
            "template_node_id": node_id,
            "title": slide_def.get("title", ""),
            "body": body,
        }
        speaker_notes = slide_def.get("speaker_notes")
        if speaker_notes:
            # Figma Slides supports speaker notes per slide
            record["speaker_notes"] = speaker_notes
            manifest.add("LOSSLESS", slide_id, "speaker_notes",
                         f"speaker notes ({len(speaker_notes)} chars) preserved.")

        transitions = slide_def.get("transitions")
        if transitions:
            manifest.add(
                "DROPPED", slide_id, "transitions",
                "transitions are an IR-only narrative-connective-tissue field; "
                "no native Figma representation.",
            )

        slide_records.append(record)

    return slide_records, manifest


def emit_yaml(slide_records: list[dict], file_key: str, deck_title: str) -> str:
    """Emit the per-slide YAML envelope the publisher consumes."""
    envelope = {
        "deck_title": deck_title,
        "file_key": file_key,
        "slides": slide_records,
    }
    return yaml.safe_dump(envelope, sort_keys=False, allow_unicode=True)


# ---- CLI ----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Translate a Deck IR + template profile into per-slide YAML the "
            "Figma MCP publisher consumes. Emits the YAML plus a markdown "
            "loss manifest and JSON sidecar."
        )
    )
    parser.add_argument("--ir", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", required=True, help="Output per-slide YAML path")
    args = parser.parse_args()

    ir_path = Path(args.ir).expanduser()
    profile_path = Path(args.profile).expanduser()
    out_path = Path(args.out).expanduser()

    try:
        slide_records, manifest = translate(ir_path, profile_path)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    yaml_text = emit_yaml(
        slide_records,
        file_key=manifest.file_key,
        deck_title=manifest.deck_title,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml_text)

    loss_md_path = out_path.with_suffix(out_path.suffix + ".loss.md")
    loss_json_path = out_path.with_suffix(out_path.suffix + ".loss.json")
    loss_md_path.write_text(manifest.to_markdown())
    loss_json_path.write_text(json.dumps(manifest.to_json(), indent=2) + "\n")

    print(f"Wrote {out_path}")
    print(f"Wrote {loss_md_path}")
    print(f"Wrote {loss_json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
