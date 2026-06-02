---
name: story-from-deck
description: Reverse-engineer a Deck IR from an existing .pptx or Figma file. Use when the user has a deck they're proud of and wants the story-publisher pipeline to operate on it — "extract the IR from this deck I already made," "I want to remix this deck," "use this old talk as the starting point for a new one." The skill extracts slide titles, body content, speaker notes, and beat structure, then produces an IR.
---

# story-from-deck

Reverse the pipeline. Given a slide artifact, recover the underlying story-level IR.

## When this skill triggers

- "Here's a .pptx I already wrote. Extract the IR."
- "I want to remix this deck."
- "Use this old talk as the starting point."
- The user uploads a deck and asks for "the underlying story" or "the structure."

## How to invoke

```bash
cd "<plugin-root>"
python adapters/story_from_deck.py /path/to/source.pptx \
  --style ted-talk \
  --out /path/to/extracted.ir.yaml
```

## How the skill works

### Stage 1 — Slide-level extraction

For each slide, capture:

- **Title** (from the title placeholder).
- **Body content** as text (concatenated body placeholder text + visible shape text).
- **Speaker notes** (verbatim).
- **Layout name** (the layout the slide references).
- **Per-shape geometry** for diagnostic purposes.

### Stage 2 — Beat inference

Each slide is tagged with a candidate beat name based on:

- Slide position in deck (first slide → `hook`; last slide → `next`).
- Layout name → IR intent (uses the same `_common.detect_intent_from_name` heuristic the extractor uses).
- IR intent → likely beat per the style's `beats.<beat>.layout_intents` reverse lookup.

The skill surfaces the inferred beat per slide and asks the user to confirm or reclassify before producing the IR.

### Stage 3 — Throughline inference

Two candidates:

1. Most-repeated meaningful noun-phrase across slide titles + speaker notes.
2. Verbatim from a slide whose layout is `callout` and beat is `claim` or `callback`.

User picks (or supplies their own).

### Stage 4 — Body-block reconstruction

Per slide, convert text content into IR body_blocks:

- Multi-line bulleted content → `kind: bullets`.
- Standalone large text → `kind: prose`.
- Numbers + units → `kind: metric`.
- Quoted text → `kind: quote`.
- Image references (placeholder names "Picture 1", etc.) → `kind: image_placeholder` with alt + intent.

### Stage 5 — Style influence

The chosen style affects:

- Which arc the skill recommends (TED-style sequencing prefers hero-journey arc).
- How densely the extracted IR allocates slides (Reynolds-zen may collapse 2-3 sparse slides into one logical beat).
- The `evidence_anchor` recommendation based on which body_block kinds dominate.

### Stage 6 — Emit IR + surface caveats

Save the IR. Note any uncertain inferences in a `<deck>.reverse-engineering.md` sidecar. Highlight:

- Slides where beat inference was ambiguous.
- Body content too dense to fit cleanly into v0.1 IR (e.g., complex diagrams).
- Image placeholders that need user-supplied alt text.

## Figma path

Driven by the Figma MCP. Stage 1 walks the file via the shallow-navigation pattern (see [`docs/FIGMA-PLUGIN-API-RULES.md`](../../docs/FIGMA-PLUGIN-API-RULES.md)). Stages 2-6 run as Python over the resulting JSON.

## Refusal patterns

- Source deck has < 4 slides — too thin to infer a story; treat as `story-from-interview` input instead.
- Source deck is mostly visuals with little text → ask the user for additional context (audience, throughline) before compiling.
- Source deck appears to be a synthesized template (from `template-synthesizer-*`) — those aren't story artifacts; redirect to template-setup.

## Composition with other skills

- **Upstream:** the source deck. May also be driven by `template-setup` when the user supplies a deck-with-implicit-pattern (the template path extracts visual patterns; this path extracts narrative patterns — they compose if the user wants both).
- **Downstream:** `slide-ir-validator` audits the recovered IR; then any renderer.
- **Style library:** chosen style affects arc + beat inference.

## v0.2 limitations

- **Text-only extraction.** Visual elements (diagrams, charts, images) are captured as placeholders with alt text inferred from neighboring captions. The skill does not OCR images or interpret charts.
- **Speaker notes are the dominant signal.** Decks without speaker notes are harder to reverse-engineer because the body content alone often can't disambiguate beats. The skill warns when notes are sparse.
- **Single-language assumption.** Beat inference heuristics assume English.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).

## Reference

- Adapter: `adapters/story_from_deck.py`.
- IR schema: `ir/schema.json`.
- Style schema: `styles/schema.json`.
