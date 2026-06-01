---
name: template-synthesizer-pptx
description: Synthesize a candidate template from a .pptx deck-with-implicit-pattern — a deck where every slide carries the user's brand identity but no structured template exists. Use this skill whenever the template-classifier verdict is "deck-with-implicit-pattern" for a pptx input. Also use when the user says "build a template from this deck," "extract the layouts from this deck," or "make this work even though I don't have a template."
---

# template-synthesizer-pptx

The remediation half of the detection-and-remediation pair. Detects the recurring visual patterns in a loose deck, derives canonical layouts, and emits a synthesized template the user can review and adopt.

This is what makes the plugin useful to the actual majority case — users who have a brand identity in their slides but never built a real template.

## When this skill triggers

- `template-classifier` returns `deck-with-implicit-pattern` for a `.pptx` source.
- The user explicitly asks "build a template from this deck" or "derive a template."
- A `template-extractor-pptx` run returns a near-empty profile because the input lacks template structure.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/template_synthesizer_pptx.py /path/to/loose-deck.pptx \
  --out /path/to/synthesized-template.pptx \
  --report /path/to/synthesizer-report.json
```

If `--report` is omitted, the JSON is written next to the .pptx as `<name>.synthesizer-report.json`.

## How the synthesis works

1. **Profile every slide.** For each slide, capture each shape's kind (text / image / other), quantized position (0.5-inch grid), quantized size, dominant font (largest size + most common family), and dominant text fill color.
2. **Compute a signature per slide.** Sort shapes by position, take a tuple of their core properties. Two slides with the same signature → same visual pattern.
3. **Cluster slides by signature.** Exact-match clustering for v0.1 (quantization makes near-matches collapse). v0.2 will move to similarity-thresholded clustering for more forgiveness.
4. **Derive layout names per cluster.** Heuristic rules:
   - 1 big text (≥80pt) + 1 small text → `Stat Block`.
   - 1 medium-big text (40-79pt) + 1 small text → `Title Slide`.
   - 1 medium text (24-39pt) + 1 small attribution → `Pull Quote`.
   - 1 header + 3 similar-width columns of text → `Three Column`.
   - 1 image + ≤2 text → `Image and Caption`.
   - 1 text only → `Section Header`.
   - Otherwise → `Custom Layout (n_text=N, n_image=M)`.
5. **Suggest IR intents** per layout name via the same pattern dictionary the extractor uses.
6. **Extract tokens.** Aggregate fonts, sizes, and colors across all slides into the synthesized profile's style_tokens.
7. **Emit synthesized .pptx.** Rename layouts in a fresh `Presentation()` master to match cluster names. v0.1 carries layout *names* only; canonical shape positions are in the JSON report.
8. **Emit synthesizer-report.json.** Per-cluster patterns + suggested layout_map + extracted tokens + v0.1 caveats.

## Output

### The synthesized `.pptx`

Carries renamed layouts matching the derived cluster names. The renderer can bind to these names via the suggested `layout_map`. v0.1 limitation: shape positions and styling from the source deck are *documented in the JSON report* but not embedded in the .pptx layouts. The renderer produces decks with the right structural skeleton but without the source deck's visual styling.

### The synthesizer-report JSON

```json
{
  "source_deck": "/path/to/loose-deck.pptx",
  "synthesized_template": "/path/to/synthesized-template.pptx",
  "n_slides": 8,
  "n_clusters": 4,
  "clusters": [
    {
      "cluster_id": 0,
      "derived_name": "Title Slide",
      "suggested_intent": "title",
      "member_slide_indices": [0, 1],
      "n_members": 2,
      "canonical_shapes": [
        {"kind": "text", "left": 457200, "top": 2057400, ...}
      ]
    },
    ...
  ],
  "suggested_layout_map": {
    "title": "Title Slide",
    "three_pillars": "Three Column",
    "metrics": "Stat Block",
    "quote": "Pull Quote"
  },
  "extracted_tokens": {
    "colors": {"primary": "#1F2A44", "secondary": "#4A5160", ...},
    "typography": {"display": {"family": "Helvetica", "size_pt": 120.0, ...}}
  },
  "v0_1_caveats": [...]
}
```

## How the orchestrator uses the output

`template-setup` Step 3 (when classifier returned `deck-with-implicit-pattern`):

1. Call this skill.
2. Show the user the cluster summary ("Detected 4 visual patterns: Title Slide, Three Column, Stat Block, Pull Quote").
3. Ask: "Adopt this as your template? [y / iterate / start over]"
4. If accepted: persist the synthesized .pptx path + the suggested `layout_map` + extracted tokens into the user's `profile.yaml`.
5. Run `template-validator` against the synthesized profile to score it; surface findings.

## What the user does after synthesis

The synthesized .pptx is a *barebones template*. For a polished result, the user can:

- **Path A (quick):** accept the synthesized template as-is. Decks render with the right structure but inherit no visual styling from the source deck.
- **Path B (recommended):** open the synthesized .pptx in PowerPoint, manually update each renamed layout's placeholders to match the canonical shape positions and styling in the JSON report. Save and re-run `template-setup`. The classifier should now report `template` with high confidence; the extractor produces a quality profile.
- **Path C (v0.2):** wait for v0.2 of this skill, which will embed canonical shape positions directly into the synthesized layouts — closing the gap between Path A and Path B.

## v0.1 limitations (be honest about these)

- **Shape embedding deferred.** v0.1 emits layout NAMES; v0.2 will embed canonical shape positions, fonts, and colors into the layouts themselves.
- **Exact-match clustering.** Two slides that differ in shape position by >0.5 inch land in separate clusters even if they're visually identical to the eye. v0.2 will use similarity-thresholded clustering.
- **No image extraction.** Image shapes are profiled (counted, positioned) but the actual images aren't copied into the synthesized template.
- **No theme synthesis.** v0.1 emits token suggestions in the report but doesn't write a proper Office theme into the synthesized .pptx. v0.2 will.
- **English-only naming heuristics.** Layout name derivation assumes English-language font/text conventions. Non-English content may produce generic "Custom Layout" names; the suggested_intent fallback still works.

These are scoped, deliberate v0.1 simplifications — not bugs. Document them upfront when surfacing the synthesizer output to the user.

## What this skill is NOT

- Not a layout designer. The synthesizer detects what's already there; it doesn't invent layouts the source deck doesn't exhibit.
- Not a brand designer. Tokens reflect what the source deck uses; the synthesizer doesn't optimize colors for accessibility or recommend palette changes.
- Not a Figma synthesizer. See `template-synthesizer-figma`.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Composition with other skills

- **Upstream:** `template-classifier` gates invocation (`deck-with-implicit-pattern` verdict).
- **Sibling:** `template-extractor-pptx` runs on the synthesized output to produce the profile entry. `template-validator` audits the resulting profile.
- **Downstream:** the renderer (`render-pptx`) consumes the profile.

## Reference

- Adapter: `adapters/template_synthesizer_pptx.py`.
- Sibling skill: `template-classifier` produces the verdict that gates this skill.
- IR layout-intent catalog: `ir/schema.json` § `layout_intent` enum.
