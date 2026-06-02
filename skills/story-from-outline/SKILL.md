---
name: story-from-outline
description: Compile a structured outline (audience, throughline, beats, evidence) into a Deck IR YAML, shaped by a chosen storytelling style. Successor to the v0.1 story-compiler skill — same outline format, now accepts a `--style` flag (or `style:` in outline frontmatter) that determines arc, beat allocation, density, and posture. Use this skill whenever the user wants to turn a written outline into structured slide content.
---

# story-from-outline

The v0.2 successor to `story-compiler`. Same outline contract; now style-aware.

## When this skill triggers

Same triggers as the v0.1 `story-compiler`:

- "Draft a deck from this outline."
- "Turn my notes into slides."
- "Build the structure for a 20-minute talk on X."

Plus the style-aware triggers:

- "Compile this in TED-talk style."
- "Use the Tufte data style for this readout."

## Required inputs

Unchanged from `story-compiler`:

- `audience` (primary + prior_knowledge)
- `throughline`
- `arc` (optional — defaults from the chosen style's `default_arc`)
- `evidence_anchor`
- `beats` (ordered list)
- `duration_min` (optional but recommended)

Plus optionally:

- `style` — string. Name of the storytelling style to apply. If unset, defaults to `default-balanced`. See `storytelling-style-library`.

## Style as frontmatter

```yaml
---
style: ted-talk
audience:
  primary: "VP of Design, Series C"
  prior_knowledge: warm
throughline: "Our growth model has plateaued; the next $40M is in the middle market."
arc: provocation
evidence_anchor: framework
duration_min: 20
---

## hook
The growth model that got us here will not get us to the next milestone.

## context
...
```

## Style as CLI flag

```bash
cowork run story-from-outline --input my-talk.outline.md --style ted-talk --out my-talk.ir.yaml
```

Frontmatter `style:` wins over the CLI flag if both are set.

## How the style is applied

1. **Arc resolution.** If the outline names an arc, validate it's in the style's `arc_set`. If not, surface a warning + suggest the style's `default_arc`. If outline omits arc, use the style's `default_arc`.
2. **Slide count target.** `n_slides_target = duration_min × style.density.slides_per_minute`. Used to pace beat allocation.
3. **Per-beat allocation.** For each beat, honor the style's `beats.<beat>.min` and `.max` counts.
4. **Layout-intent selection.** When the compiler picks a `layout_intent` for a slide, it draws from the style's `beats.<beat>.layout_intents` list — top of the list is preferred. Density rules further constrain (e.g., `reynolds-zen` won't pick `metrics` with bullets even though both are technically allowed).
5. **Body block density.** Compiler respects `style.density.max_body_blocks_per_slide`.
6. **Posture.** Surfaces `style.voice_notes` to the user; influences default speaker_notes voice.

## Refusal patterns (unchanged from v0.1)

- Missing audience / throughline / evidence anchor → ask, don't invent.
- "Make me a deck" with no inputs → ask for at least audience + throughline.
- Vague throughline → ask for compression to one sentence.

## Output

Same as `story-compiler`: a Deck IR YAML conforming to `ir/schema.json`. Style choice does NOT appear in the IR (styles are compile-time, not artifact-time). It's recorded in `notes/` for the user's record-keeping if helpful.

## Composition

- **Upstream:** `storytelling-style-library` resolves the style file.
- **Validation:** `slide-ir-validator` runs against the output before handing back.
- **Downstream:** any renderer (`render-pptx`, `render-figma`) consumes the IR.

## Reference

- Style schema: `styles/schema.json`.
- v0.1 outline contract: same as `story-compiler` — see `ir/schema.json` for the IR shape.
