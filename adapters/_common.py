"""
_common.py — shared constants, helpers, and dataclasses for slide-publisher
adapters.

Single source of truth for everything previously duplicated across
extractor / synthesizer / validator / renderer / remediator. Update here →
all adapters pick up the change.

**Format-pluggable.** Nothing in this module is pptx-specific or figma-
specific. v0.2 adds gslides as a third format; the contract a format adapter
must satisfy is documented as the `FormatAdapter` Protocol below.

Anonymity: ships in the public plugin. No organization patterns, no defaults
that identify any specific user.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ============================================================================
# IR catalogs — keep in sync with ir/schema.json
# ============================================================================

LAYOUT_INTENTS: list[str] = [
    "title",
    "section_break",
    "claim_with_evidence",
    "three_pillars",
    "comparison",
    "quote",
    "image_with_caption",
    "metrics",
    "timeline",
    "callout",
]

BEATS: list[str] = [
    "hook", "context", "problem", "claim", "evidence", "tension",
    "resolution", "callback", "next",
]

BODY_BLOCK_KINDS: list[str] = [
    "prose", "bullets", "metric", "quote", "image_placeholder", "diagram_placeholder",
]


def render_block_to_text(
    kind: str,
    content: Any,
    manifest=None,
    slide_id: str = "",
    idx: int = 0,
) -> str | None:
    """Render a single IR body_block to its text representation.

    Single source of truth for text flattening, used by:
      - pptx_renderer.populate_body — populates text frame placeholders.
      - uat/server.py Figma payload converter — keeps cross-renderer text consistent.
      - story_from_deck reverse-engineering — preview blocks as text.

    The mapping is deterministic — same input always produces same string.
    When `manifest` is supplied (must support `.add(category, slide_id, source,
    reason)`), LOSSY/DROPPED entries are recorded for non-text kinds.

    Returns None if the block can't be represented (manifest gets a DROPPED
    entry in that case).
    """
    if kind == "prose":
        return str(content) if content is not None else ""
    if kind == "bullets":
        if isinstance(content, list):
            return "\n".join(f"• {item}" for item in content)
        return None
    if kind == "metric":
        if isinstance(content, dict):
            label = content.get("label", "")
            value = content.get("value", "")
            unit = content.get("unit", "")
            comparison = content.get("comparison", "")
            head = f"{value} {unit}".strip() if unit else str(value)
            line = " — ".join(p for p in (head, label) if p)
            if comparison:
                line += f"\n  ({comparison})"
            return line
        return None
    if kind == "quote":
        if isinstance(content, dict):
            text = content.get("text", "")
            attribution = content.get("attribution", "")
            out = f"“{text}”"
            if attribution:
                out += f"\n— {attribution}"
            return out
        return None
    if kind == "image_placeholder":
        if manifest is not None:
            manifest.add(
                "LOSSY", slide_id, f"body_blocks[{idx}].kind=image_placeholder",
                "image_placeholder rendered as caption text only; image asset "
                "is the user's responsibility post-render.",
            )
        if isinstance(content, dict):
            return f"[IMAGE: {content.get('alt', '')}]\n{content.get('intent', '')}"
        return "[IMAGE]"
    if kind == "diagram_placeholder":
        if manifest is not None:
            manifest.add(
                "LOSSY", slide_id, f"body_blocks[{idx}].kind=diagram_placeholder",
                "diagram_placeholder rendered as caption text only; the diagram "
                "is the user's responsibility post-render.",
            )
        if isinstance(content, dict):
            return f"[DIAGRAM: {content.get('alt', '')}]\n{content.get('intent', '')}"
        return "[DIAGRAM]"
    if manifest is not None:
        manifest.add(
            "DROPPED", slide_id, f"body_blocks[{idx}].kind={kind}",
            f"unknown body_block kind '{kind}'; dropped.",
        )
    return None


# Title-length thresholds per layout intent — used by renderers (and the visual-QA
# anomaly classifier) to detect when an IR title will overflow a tight title
# placeholder. Conservative defaults; templates with bigger title bands won't
# trigger. Override per profile if needed.
TITLE_LENGTH_THRESHOLDS: dict[str, int] = {
    "title": 60,
    "section_break": 50,
    "callout": 80,
    "claim_with_evidence": 80,
    "three_pillars": 70,
    "comparison": 65,
    "quote": 90,            # quotes can be long
    "image_with_caption": 60,
    "metrics": 60,
    "timeline": 60,
}


def check_title_overflow(
    title: str,
    intent: str,
    manifest=None,
    slide_id: str = "",
) -> bool:
    """Check if a title exceeds the layout intent's recommended max length.

    When `manifest` is supplied and the title overflows, an ANNOTATED entry
    is recorded with the threshold + actual length + a remediation suggestion.

    Returns True when overflow detected (caller can use the boolean for any
    additional logic; the manifest entry is the user-facing signal).
    """
    if not title:
        return False
    threshold = TITLE_LENGTH_THRESHOLDS.get(intent, 80)
    if len(title) <= threshold:
        return False
    if manifest is not None:
        manifest.add(
            "ANNOTATED", slide_id, "title_length",
            f"title is {len(title)} chars; layout '{intent}' fits cleanly up to "
            f"{threshold}. Consider shortening or picking a less-constrained "
            f"intent to avoid wrapping/overflow in tight title placeholders "
            f"(e.g., Atlas's speech-bubble title shape).",
        )
    return True

ARC_VALUES: list[str] = [
    "problem-first", "situation-first", "provocation", "case-led",
    "reverse-chronological",
]

EVIDENCE_ANCHORS: list[str] = ["numbers", "story", "demo", "framework", "hybrid"]


# ============================================================================
# Pattern dictionaries (heuristic name matching)
# ============================================================================

# Maps IR intent → list of substring patterns that suggest that intent.
# First match wins; used by extractor, validator, synthesizer, remediator.
INTENT_PATTERNS: dict[str, list[str]] = {
    "title": ["title slide", "title", "cover", "opening"],
    "section_break": ["section header", "section", "divider", "chapter", "break"],
    "claim_with_evidence": [
        "title and content", "content", "body", "claim", "supporting",
    ],
    "three_pillars": ["three column", "3 column", "three", "pillars", "tri"],
    "comparison": ["comparison", "compare", "two column", "2 column", "side by side"],
    "quote": ["pull quote", "quote", "blockquote", "testimonial"],
    "image_with_caption": [
        "image and caption", "picture and caption", "image", "picture", "photo",
    ],
    "metrics": ["stat", "metric", "kpi", "number block", "data"],
    "timeline": ["timeline", "chronology", "milestone", "roadmap"],
    "callout": ["callout", "big statement", "headline", "punchline", "lockup"],
}

# Canonical name to give a layout when synthesizing or remediating for a
# specific intent.
INTENT_TO_HEURISTIC_NAME: dict[str, str] = {
    "title": "Title Slide",
    "section_break": "Section Header",
    "claim_with_evidence": "Title and Content",
    "three_pillars": "Three Column",
    "comparison": "Comparison",
    "quote": "Pull Quote",
    "image_with_caption": "Image and Caption",
    "metrics": "Stat Block",
    "timeline": "Timeline",
    "callout": "Big Statement",
}

# Fallback ordering when a renderer's profile lacks an intent's mapping.
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


# ============================================================================
# Token roles + defaults
# ============================================================================

COLOR_TOKEN_ROLES: list[str] = [
    "primary", "secondary", "accent", "text-primary", "text-secondary",
    "surface", "surface-muted", "accent-warn",
]

TYPE_TOKEN_ROLES: list[str] = [
    "display", "heading-1", "heading-2", "heading-3", "body", "caption",
]

# Generic palette used by remediators when the user's file has zero tokens.
# Brand-neutral; user is expected to customize.
DEFAULT_PALETTE: dict[str, str] = {
    "primary": "#1F2A44",
    "secondary": "#3F6AB1",
    "accent": "#E2A03F",
    "text-primary": "#111418",
    "text-secondary": "#5B6470",
    "surface": "#FFFFFF",
    "surface-muted": "#F4F5F8",
}

DEFAULT_TYPEFACE: str = "Inter"


# ============================================================================
# Quantization helpers
# ============================================================================

def quantize(val: int | float | None, q: int) -> int:
    """Round val to the nearest multiple of q. None → 0."""
    if val is None:
        return 0
    return int(round(val / q) * q)


# Common quantum sizes used by synthesizer/clustering.
POSITION_QUANTUM_EMU: int = 457200      # 0.5 inch
POSITION_QUANTUM_PX: int = 16           # Figma px
FONT_SIZE_QUANTUM_PT: int = 4


# ============================================================================
# Severity helpers (validator + remediator)
# ============================================================================

GREEN, YELLOW, RED = "green", "yellow", "red"
SEVERITIES = (GREEN, YELLOW, RED)


def severity_from_fraction(frac: float, *, green_at: float, yellow_at: float) -> str:
    if frac >= green_at:
        return GREEN
    if frac >= yellow_at:
        return YELLOW
    return RED


def severity_from_count(count: int, *, green_at: int, yellow_at: int) -> str:
    if count >= green_at:
        return GREEN
    if count >= yellow_at:
        return YELLOW
    return RED


# ============================================================================
# Loss manifest (shared between render-pptx and figma-yaml-emitter)
# ============================================================================

LOSSLESS, LOSSY, DROPPED, ANNOTATED = "LOSSLESS", "LOSSY", "DROPPED", "ANNOTATED"
LOSS_CATEGORIES = (LOSSLESS, LOSSY, DROPPED, ANNOTATED)


@dataclass
class LossEntry:
    category: str
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
    """Common manifest shape for both renderers.

    Concrete subclasses set `renderer` and may add format-specific fields
    (template_path for pptx, file_key for figma).
    """
    deck_title: str = ""
    rendered_at: str = ""
    renderer: str = ""
    entries: list[LossEntry] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def add(self, category: str, slide_id: str | None,
            field_name: str, detail: str) -> None:
        self.entries.append(LossEntry(category, slide_id, field_name, detail))

    def counts(self) -> dict[str, int]:
        return {
            cat.lower(): sum(1 for e in self.entries if e.category == cat)
            for cat in LOSS_CATEGORIES
        }

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "deck_title": self.deck_title,
            "rendered_at": self.rendered_at,
            "renderer": self.renderer,
            "summary": self.counts(),
            "entries": [e.to_dict() for e in self.entries],
        }
        out.update(self.extra)
        return out

    def to_markdown(self) -> str:
        counts = self.counts()
        summary = (
            f"> Summary: {counts['lossless']} lossless, {counts['lossy']} lossy, "
            f"{counts['dropped']} dropped, {counts['annotated']} annotated.\n\n"
        )
        lines = [
            summary,
            f"# Loss manifest — {self.deck_title}",
            "",
            f"- Rendered: {self.rendered_at}",
            f"- Renderer: `{self.renderer}`",
        ]
        for k, v in self.extra.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
        for cat in LOSS_CATEGORIES:
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


# ============================================================================
# Layout-map helpers (used by renderers + remediators)
# ============================================================================

def detect_intent_from_name(name: str) -> str | None:
    """Return the IR intent a layout name matches, or None.

    Used by classifier (signal), extractor (mapping), remediator (skip
    already-correct names).
    """
    lower = name.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for p in patterns:
            if p in lower:
                return intent
    return None


def infer_layout_map(layout_names: list[str]) -> dict[str, str]:
    """Map IR intent → first matching layout name. Each name used at most once."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for intent in LAYOUT_INTENTS:
        for pattern in INTENT_PATTERNS[intent]:
            for name in layout_names:
                if name in used:
                    continue
                if pattern in name.lower():
                    mapping[intent] = name
                    used.add(name)
                    break
            if intent in mapping:
                break
    return mapping


def effective_coverage(layout_map: dict[str, str]) -> tuple[int, list[str]]:
    """Count IR intents that are EITHER directly mapped OR can resolve through
    the documented fallback chain.

    Industry-standard templates (Microsoft built-ins, Google Slides themes,
    Keynote themes) ship 8-12 structural layouts that don't carry our narrative
    intent names ('three_pillars', 'pull_quote', 'stat_block'). Those intents
    still RENDER cleanly through their fallback (typically `claim_with_evidence`
    via 'Title and Content'). Counting them as covered reflects reality.

    Returns (n_effectively_covered, list_of_uncovered_intents).
    """
    covered = set(layout_map.keys())
    changed = True
    while changed:
        changed = False
        for intent in LAYOUT_INTENTS:
            if intent in covered:
                continue
            for fb in LAYOUT_FALLBACKS.get(intent, []):
                if fb in covered:
                    covered.add(intent)
                    changed = True
                    break
    uncovered = [i for i in LAYOUT_INTENTS if i not in covered]
    return len(covered), uncovered


def quality_score(
    *,
    layout_map: dict[str, str],
    n_layouts: int,
    n_color_tokens: int,
    n_type_tokens: int,
) -> int:
    """Weighted heuristic used by extractors across all formats.

    Uses *effective* layout coverage (direct + fallback) per the Microsoft-
    themes validation finding — narrative intents like `three_pillars` count
    as covered if their fallback chain lands on a mapped intent.

    50% effective coverage, 20% catalog breadth, 15% color, 15% type.
    """
    n_covered, _ = effective_coverage(layout_map)
    layout_coverage = n_covered / len(LAYOUT_INTENTS) if LAYOUT_INTENTS else 0.0
    layout_breadth = min(1.0, n_layouts / 10.0)
    color_completeness = min(1.0, n_color_tokens / len(COLOR_TOKEN_ROLES))
    type_completeness = min(1.0, n_type_tokens / len(TYPE_TOKEN_ROLES))
    score = (
        0.50 * layout_coverage
        + 0.20 * layout_breadth
        + 0.15 * color_completeness
        + 0.15 * type_completeness
    )
    return int(round(score * 100))


# ============================================================================
# Layout-name heuristic (used by synthesizers across formats)
# ============================================================================

def derive_layout_name(*, n_text_shapes: int, n_image_shapes: int,
                       font_sizes_desc: list[int]) -> str:
    """Derive a canonical layout name from cluster signature properties.

    Format-agnostic — works on any shape set with text/image counts and
    a sorted font-size list. Used by pptx and figma synthesizers; gslides
    plugs in with the same call shape.
    """
    if not (n_text_shapes + n_image_shapes):
        return "Blank"
    largest = font_sizes_desc[0] if font_sizes_desc else 0
    second = font_sizes_desc[1] if len(font_sizes_desc) > 1 else 0
    # Order matters: check huge-font cases before title (so a giant number
    # isn't misnamed as a title).
    if n_text_shapes == 2 and n_image_shapes == 0:
        if largest >= 80:
            return "Stat Block"
        if largest >= 40 and second <= 24:
            return "Title Slide"
        if largest >= 24 and second <= 16:
            return "Pull Quote"
    if n_text_shapes == 4 and n_image_shapes == 0:
        return "Three Column"
    if n_text_shapes == 1 and n_image_shapes == 0:
        return "Section Header"
    if n_image_shapes >= 1 and n_text_shapes <= 2:
        return "Image and Caption"
    return f"Custom Layout (n_text={n_text_shapes}, n_image={n_image_shapes})"


def suggest_intent_from_name(name: str) -> str:
    """Map a (derived or extracted) layout name to an IR intent.

    Defaults to `claim_with_evidence` (the universal default) when no
    pattern matches.
    """
    detected = detect_intent_from_name(name)
    return detected if detected else "claim_with_evidence"


# ============================================================================
# Diagnose helper (used by extractors + synthesizers across formats)
# ============================================================================

def diagnose_coverage(*, n_layouts_inspected: int, layout_map: dict[str, str],
                     n_color_tokens: int, n_type_tokens: int,
                     format_label: str = "template") -> list[str]:
    """Format-agnostic human-readable findings for the extractor/synthesizer.

    `format_label` lets each adapter say "pptx layout", "figma frame", etc.
    """
    findings: list[str] = []
    if n_layouts_inspected == 0:
        findings.append(f"No {format_label}s inspected. Is the input valid?")
    elif n_layouts_inspected < 5:
        findings.append(
            f"Only {n_layouts_inspected} {format_label}s found. Templates "
            "typically have 8-12; consider extending the catalog."
        )
    missing = [i for i in LAYOUT_INTENTS if i not in layout_map]
    if missing:
        findings.append(
            f"{len(missing)} of {len(LAYOUT_INTENTS)} IR layout intents have "
            f"no matching {format_label}: {', '.join(missing)}. Renderers "
            "will fall back to 'nearest available' and log substitutions in "
            "the loss manifest."
        )
    if n_color_tokens == 0:
        findings.append(
            "No explicit color tokens extracted. The template may rely on "
            "theme/named-style colors only; renderers inherit at render time."
        )
    if n_type_tokens == 0:
        findings.append(
            "No typography tokens extracted. The template may not define "
            "explicit type styles."
        )
    if n_layouts_inspected > 0 and len(layout_map) == len(LAYOUT_INTENTS):
        findings.append(
            f"All {len(LAYOUT_INTENTS)} IR layout intents have a matching "
            f"{format_label}. Clean coverage."
        )
    return findings


# ============================================================================
# Format adapter Protocol — what each format must expose
# ============================================================================
#
# v0.1: pptx (python-pptx backend), figma (MCP backend).
# v0.2: gslides (Slides API / MCP backend).
#
# A format adapter is a module exposing the functions below; the generic
# extractor / synthesizer / validator / remediator dispatch on a format key
# and call into the matching adapter module.

@runtime_checkable
class FormatAdapter(Protocol):
    """Minimum surface every format adapter implements.

    All current per-format adapter modules conform structurally; the Protocol
    documents the contract for v0.2 gslides without imposing inheritance.
    """

    FORMAT_NAME: str       # "pptx" | "figma" | "gslides"

    def collect_layouts(self, source: Any) -> list[Any]:
        """Return a sequence of layout-shaped objects from the source.

        For pptx, source = Presentation; layouts = master.slide_layouts.
        For figma, source = MCP walk output; layouts = slide_templates.
        For gslides (v0.2), source = Slides API response; layouts =
        presentation.layouts.
        """
        ...

    def layout_name(self, layout: Any) -> str:
        ...

    def collect_color_tokens(self, source: Any) -> dict[str, str]:
        """Returns token_name → "#RRGGBB"."""
        ...

    def collect_type_tokens(self, source: Any) -> dict[str, dict[str, Any]]:
        """Returns role_name → {family, size_pt, weight, line_height?}."""
        ...
