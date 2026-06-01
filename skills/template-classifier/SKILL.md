---
name: template-classifier
description: Detect whether a .pptx or Figma file is a structured template, a deck-with-implicit-pattern (visual identity in slides, no real template structure), or mixed. Use this skill at the start of template-setup, every time the user supplies a source file — before extraction. Also use when the user asks "is this a template?", "does my deck have a template?", or "why is the extractor returning a near-empty profile?"
---

# template-classifier

The first hop in the template-setup wizard. Tells the user (and the orchestrator) what they're holding: a real template, a deck with an implicit pattern (no real template structure but a clear visual identity), or something in between.

Without this step, the extractor on a deck-shaped input returns a near-empty profile and the user is confused because they *do* have a brand. The classifier surfaces the diagnosis and routes the orchestrator to the synthesizer when needed.

## When this skill triggers

- Invoked by `template-setup` at Step 2 (classification), every time.
- The user pastes a file and asks "is this a template?" or "why didn't the extractor work?"
- A render skill is failing with low-quality output and the user wants to diagnose whether the template was the problem.

## How to invoke

For pptx:

```bash
cd "<plugin-root>"
python adapters/template_classifier.py /path/to/file.pptx
```

For figma: the classifier runs as a Plugin API recipe via the Figma MCP (no Python adapter). See "Figma classification" below.

## Output

```json
{
  "format": "pptx",
  "classification": "template" | "deck-with-implicit-pattern" | "mixed",
  "confidence": 0.0,
  "signals": {
    "n_slides": 8,
    "n_layouts_available": 11,
    "n_layouts_used": 1,
    "layout_diversity_ratio": 0.125,
    "default_layout_ratio": 1.0,
    "direct_overrides_estimate": 47,
    "direct_overrides_per_slide": 5.88,
    "layout_name_semantic_richness": 0.18
  },
  "diagnosis": [
    "Layout diversity ratio is 0.13 — most slides share the same layout, suggesting a deck written on default layouts.",
    "100% of slides reference stock layouts (Title Slide, Title and Content, Blank)...",
    "Verdict: 'deck-with-implicit-pattern' (template-ness score 0.18, confidence 0.64). Recommend running template-synthesizer-pptx..."
  ]
}
```

## How the signals are derived

| Signal | What it measures | Why it matters |
|---|---|---|
| `n_slides` | Total slides | Sample size — confidence is lower for very small decks. |
| `n_layouts_available` | Layouts defined in masters | Templates typically have ≥8; sparse layout sets favor "deck." |
| `n_layouts_used` | Distinct layouts actually referenced by slides | Templates spread slides across layouts; decks concentrate. |
| `layout_diversity_ratio` | `n_layouts_used / n_slides` | Higher = more template-like. <0.2 strongly suggests a deck. |
| `default_layout_ratio` | Fraction of slides on stock layouts (Title Slide, Title and Content, Blank, etc.) | High = deck. >0.7 strongly suggests a deck. |
| `direct_overrides_estimate` | Slide shapes that are NOT placeholders | Hand-positioned text boxes / shapes add to this. Decks have many. |
| `direct_overrides_per_slide` | Same, normalized | >3 per slide is a strong deck signal. |
| `layout_name_semantic_richness` | Fraction of layout names containing IR-intent words (`three`, `quote`, `metric`, etc.) | Templates designed for slide-publisher carry intent in their names. Decks usually don't. |

## Scoring

The classifier computes a weighted "template-ness" score from the signals:

- `diversity` weight 0.30 — how varied the slides' layout choices are.
- `non_default` weight 0.25 — inverse of default-layout ratio.
- `low_overrides` weight 0.20 — fewer hand-positioned shapes → more template-like.
- `semantic_richness` weight 0.15 — layout names that match IR intent patterns.
- `layout_breadth` weight 0.10 — does the catalog have enough breadth (≥5 layouts used).

Thresholds:

- ≥ 0.65 → `template`
- ≤ 0.35 → `deck-with-implicit-pattern`
- otherwise → `mixed`

Confidence is `|template_ness - 0.5| × 2` — distance from the boundary.

## What the orchestrator does with the verdict

`template-setup` Step 3 branches on classification:

- **`template`** → skip synthesis; call `template-extractor-<format>` directly.
- **`deck-with-implicit-pattern`** → surface the diagnosis to the user, then call `template-synthesizer-<format>` to derive a template. The synthesized output goes back through the extractor + validator. The user reviews and accepts (or iterates) before the profile locks.
- **`mixed`** → surface both options to the user; let them choose.

## Figma classification

Same idea, MCP-driven. The Plugin API recipe walks the file's slides and computes:

| Signal | How to compute (shallow navigation, Rule 3) |
|---|---|
| `n_slides` | `figma.root.children` flattened across pages. |
| `n_template_frames` | Top-level FRAMEs on a "Templates" or similarly-named page, OR FRAMEs with the Heading-frame structure (Rule 3). |
| `n_named_text_styles` | `figma.getLocalTextStyles().length` |
| `n_named_color_styles` | `figma.getLocalPaintStyles().length` |
| `slides_with_heading_structure` | Slides where `children[0].children[0]` is a TEXT node (consistent with Heading-frame pattern). |
| `consistent_title_position` | Variance of title shape coordinates across slides. Low variance = template-shaped. |

Thresholds:

- ≥3 template frames AND ≥3 named styles AND consistent title positioning → `template`.
- 0 template frames AND <3 named styles AND high direct-shape count → `deck-with-implicit-pattern`.
- Otherwise → `mixed`.

The figma classifier returns the same JSON shape as the pptx classifier, but with figma-specific signals.

## What this skill is NOT

- Not a quality checker. The classifier asks "is there a template?" — `template-validator` asks "is the template good?". Different stages.
- Not deterministic. Heuristic scores can be wrong on edge cases. Confidence in the output signals when the result is shaky.
- Not a fixer. Detection only — `template-synthesizer-<format>` does the remediation.

## Anonymity (plugin policy)

This skill ships in the public plugin. The pattern dictionaries are generic; no organization-specific signals; no hard-coded user defaults. Output reflects the user's input only.

## Composition with other skills

- **Upstream:** `template-setup` invokes the classifier at Step 2.
- **Downstream:** routes to `template-extractor-<format>` (template path) or `template-synthesizer-<format>` (deck path) or both (mixed).
- **Sibling:** `template-validator` runs after extraction to score template quality. Don't confuse the two — classification gates the input; validation gates the output.

## Reference

- Adapter: `adapters/template_classifier.py` (pptx).
- Figma recipe: described in this skill; runs via Figma MCP.
