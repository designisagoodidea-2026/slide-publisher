# Loss manifest — reference

Every render in slide-publisher emits a loss manifest in two formats, alongside the rendered deck:

- `<deck>.loss.md` — human-readable.
- `<deck>.loss.json` — machine-readable.

The manifest names what was preserved exactly, what was preserved with degradation, what was dropped, and what was added by the renderer. Nothing is lost silently. If you want to know whether a render is faithful, the manifest tells you.

## Categories

| Category | Meaning |
|---|---|
| `LOSSLESS` | Preserved exactly. The output represents this IR field with no information loss. |
| `LOSSY` | Preserved with degradation. The output represents the field but reduced. Most common: layout substitution, bullet styling replaced, image_placeholder rendered as caption text. |
| `DROPPED` | Not preserved. The output has no equivalent representation for this field. Most common: deck-level story-frame fields (`audience`, `throughline`, `arc`, `evidence_anchor`, `duration_min`) and IR-only fields (`transitions`). |
| `ANNOTATED` | Added by the renderer, not present in the IR. Most common: image/diagram placeholder captions the renderer inserts to mark where assets should go. |

## Markdown format

```
> Summary: 11 lossless, 2 lossy, 6 dropped, 0 annotated.

# Loss manifest — <deck title>

- Rendered: 2026-06-01T18:40:06
- Renderer: `render-pptx`
- Template: `tests/fixtures/synthetic-template.pptx`

## LOSSLESS (11)

- **deck-level / deck.title** — deck title applied to pptx core properties.
- **slide `the-headline` / speaker_notes** — speaker notes (137 chars) preserved.
- ...

## LOSSY (2)

- **slide `kill-criteria` / layout_intent** — intent 'three_pillars' had no mapping; substituted to 'claim_with_evidence' via the documented fallback chain.
- **slide `the-integration-step` / body_blocks[0].kind=image_placeholder** — image_placeholder rendered as caption text only; image content is the user's responsibility post-render.

## DROPPED (6)

- **deck-level / deck.audience** — 'audience' has no native .pptx representation; preserved only in the loss manifest...
- ...
```

The summary block at the top gives you the count by category at a glance. The body groups entries by category, then lists each entry as `**<scope> / <field>** — <detail>`.

## JSON format

```json
{
  "deck_title": "Design system at 12 months",
  "rendered_at": "2026-06-01T18:40:06",
  "renderer": "render-pptx",
  "template_path": "tests/fixtures/synthetic-template.pptx",
  "summary": {
    "lossless": 11,
    "lossy": 2,
    "dropped": 6,
    "annotated": 0
  },
  "entries": [
    {
      "category": "LOSSLESS",
      "slide_id": null,
      "field": "deck.title",
      "detail": "deck title applied to pptx core properties."
    },
    {
      "category": "LOSSY",
      "slide_id": "kill-criteria",
      "field": "layout_intent",
      "detail": "intent 'three_pillars' substituted..."
    },
    ...
  ]
}
```

Each entry carries `category`, `slide_id` (or null for deck-level), `field`, and `detail`. Tools can filter, group, or diff manifests by these fields.

## How to read a manifest

### Healthy patterns

| Category | Typical count | Interpretation |
|---|---|---|
| LOSSLESS | 1 + N (one per slide) | Most content preserved. Each per-slide entry confirms one stage of the render. |
| LOSSY | 0-3 | Some layout substitutions or styling drift. Acceptable unless you're chasing pixel parity. |
| DROPPED | 4-6 | Deck-level story-frame fields. These are *expected* drops — they have no native .pptx / Figma representation. They live in the manifest so the speaker doesn't lose them. |
| ANNOTATED | 0-N | Renderer additions. Rare in pptx; more common in Figma when the publisher adds continuation markers. |

### Warning signs

- **`DROPPED` count is 0.** Suspicious — the deck-level story-frame fields should always be dropped into the manifest, not silently absorbed. A renderer reporting 0 drops is either misconfigured or has a bug.
- **`LOSSY` count > 10.** The template profile likely needs work. Expect heavy layout substitution when:
  - The template covers fewer than 7 of the 10 IR layout intents.
  - The IR uses lots of `image_placeholder` / `diagram_placeholder` blocks.
  - The template has weak style hierarchy (validator's `style_hierarchy` finding).
- **A single slide has more than ~5 entries.** That slide is doing a lot of compromising. Look at the IR — is the layout intent wrong for the beat? Should the body blocks be restructured?
- **`ANNOTATED` count is unusually high.** The renderer is filling gaps the IR didn't specify. Often a sign that body blocks lack content fields that the layout's placeholders expect.

## Diffing manifests across renders

Two manifests can be compared to see what changed between renders. Useful when:

- Iterating on the IR — did your last edit fix the lossy substitution it was meant to fix?
- Migrating templates — does the new template profile reduce drops, or just shift them around?
- Comparing pptx vs figma — which renderer is more faithful for this specific deck?

The JSON format is built for this. A simple diff:

```bash
diff <(jq '.entries' deck.pptx.loss.json) <(jq '.entries' deck.figma.yaml.loss.json)
```

## How the renderers categorize

Each renderer follows the same conventions, but the field-to-category mapping differs slightly:

### render-pptx

| IR field | Category |
|---|---|
| `deck.title` | LOSSLESS (applied to core_properties) |
| `deck.audience`, `deck.throughline`, `deck.arc`, `deck.evidence_anchor`, `deck.duration_min`, `deck.voice_constraints` | DROPPED (no native pptx representation) |
| `slide.title` (with a layout title placeholder) | LOSSLESS |
| `slide.title` (no title placeholder) | DROPPED |
| `slide.layout_intent` (mapped cleanly) | LOSSLESS |
| `slide.layout_intent` (substituted via fallback chain) | LOSSY |
| `slide.body_blocks[*].kind ∈ {prose, bullets, quote}` | LOSSLESS for content; LOSSY for template-defined styling collapse |
| `slide.body_blocks[*].kind = metric` | LOSSY (typeset, not charted) |
| `slide.body_blocks[*].kind ∈ {image_placeholder, diagram_placeholder}` | LOSSY (caption text only; asset is user's responsibility) |
| `slide.body_blocks[*].kind = unknown` | DROPPED |
| `slide.speaker_notes` | LOSSLESS |
| `slide.transitions` | DROPPED (IR-only narrative connective tissue) |

### render-figma

Same as render-pptx for most fields. Differences:

| Field | Difference |
|---|---|
| `slide.layout_intent` (no mapping at all) | DROPPED (slide is skipped by the publisher), where pptx falls back to first available layout |
| `slide.body_blocks[*]` (image/diagram placeholders) | ANNOTATED rather than LOSSY (Figma renders the caption as a real frame the user can replace) |
| Stage-2 publisher additions | ANNOTATED |

## Adopting the manifest in tooling

The JSON shape is stable and machine-readable. If you build downstream tooling — a deck-quality dashboard, a CI check that gates IRs on manifest health, a manifest aggregator across a folder of decks — the JSON is the contract.

The markdown is for humans. Render it in PRs, attach it to slide-review threads, use it as the explanation when someone asks "why does this look slightly different than my template."

## Reference

- pptx renderer source: `adapters/pptx_renderer.py`.
- Figma emitter source: `adapters/figma_yaml_emitter.py`.
- IR schema: `ir/schema.json` (the source of truth for which fields exist).
- Translation-doctrine reference: the categories mirror the convention used for general-purpose tracking-system translation; the same shape works for any heterogeneous-target translation.
