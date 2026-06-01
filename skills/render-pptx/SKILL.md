---
name: render-pptx
description: Render a validated Deck IR into a .pptx using the user's template profile. Emits the deck plus a markdown loss manifest and JSON sidecar. Use this skill any time the user wants a PowerPoint output from a slide-publisher IR — "render to pptx," "make the PowerPoint," "publish as .pptx," "build the deck." Also use automatically when the user's preferred_output is pptx and they've just compiled an IR with story-compiler.
---

# render-pptx

Consume a validated IR + a template profile, produce a `.pptx` plus the loss manifest. Renderer for one of v0.1's two output formats (the other is render-figma).

## When this skill triggers

- The user says "render to pptx," "make the deck," "publish as PowerPoint."
- A story-compiler invocation has just completed and the user's `preferred_output` in their profile is `pptx`.
- A render-figma call hit an error and the user wants to try the other format.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/pptx_renderer.py \
  --ir /path/to/deck.ir.yaml \
  --profile ~/.cowork/plugins/slide-publisher/profile.yaml \
  --out /path/to/deck.pptx
```

Outputs three files:

- `deck.pptx` — the rendered deck.
- `deck.pptx.loss.md` — human-readable loss manifest.
- `deck.pptx.loss.json` — machine-readable sidecar.

Both loss artifacts land next to the .pptx.

## Pre-flight

Before rendering, the renderer assumes:

1. **IR is schema-valid.** Run `slide-ir-validator --strict` on the IR first. Renderer behavior is undefined on invalid IRs.
2. **Template profile is structurally valid.** Run `template-validator --strict --format pptx` against the profile's `templates.pptx.path`. If validator returns `fail`, address findings before rendering or accept the loss the manifest will document.
3. **python-pptx and pyyaml are installed.** Renderer fails fast (exit 2) if either is missing.

The renderer does not run these pre-flights itself — the orchestrator (`template-setup` for first-time, or the user's own compile flow) is responsible. Renderer should be idempotent and fail predictably.

## Layout resolution

Each IR slide carries a `layout_intent`. The renderer:

1. Looks up the intent in `profile.templates.pptx.layout_map`.
2. If the mapped layout exists in the template, uses it. **Recorded as LOSSLESS.**
3. If the mapped layout name doesn't exist (template drift), falls back per `LAYOUT_FALLBACKS` table in the adapter. **Recorded as LOSSY** with the substitution named.
4. If no fallback maps anything either, falls back to `claim_with_evidence` (the universal default). **Recorded as LOSSY.**
5. If that's also missing, uses the first available layout in the template. **Recorded as LOSSY** with the layout name surfaced.

Renderer never silently picks a layout. Every substitution is in the manifest.

## Body-block rendering

For v0.1, body blocks are concatenated into the slide's first body placeholder (`placeholder_format.idx > 0`). Per-block strategy:

| kind | Rendered as | Loss profile |
|---|---|---|
| `prose` | string in placeholder | LOSSLESS |
| `bullets` | bulleted list (•-prefixed lines) | LOSSY — template's bullet styling may be overridden |
| `metric` | `"value unit — label\n  (comparison)"` | LOSSY — no chart, just typeset |
| `quote` | `"\"text\"\n— attribution"` | LOSSLESS for content; LOSSY for template-defined quote styling |
| `image_placeholder` | `"[IMAGE: alt]\nintent"` text | LOSSY — no actual image; user's responsibility post-render |
| `diagram_placeholder` | `"[DIAGRAM: alt]\nintent"` text | LOSSY — same as above |

v0.2 will add: per-block placeholder allocation (one body block → one placeholder when the layout supports multiples), bullet-list native rendering, metric-as-chart rendering for `evidence_anchor: numbers` decks.

## Loss-manifest categories

Mirrors the translation-engine convention:

- **LOSSLESS** — preserved exactly. The .pptx faithfully represents the IR field.
- **LOSSY** — preserved with degradation. The .pptx represents the IR field but information is reduced (e.g., bullet styling replaced, layout substituted).
- **DROPPED** — not preserved. The .pptx has no equivalent (e.g., `deck.throughline` has no native pptx home; `transitions` are IR-only).
- **ANNOTATED** — added by the renderer, not present in the IR. (Rare in pptx — usually visual scaffolding the user can ignore.)

## Loss manifest — what's expected

For a typical IR rendered through a well-fitting template profile, expect:

| Category | Typical count | Why |
|---|---|---|
| LOSSLESS | 1 + N (slide bodies, speaker notes, deck.title) | Most content preserves cleanly. |
| LOSSY | 0-N (image/diagram placeholders, layout substitutions) | Depends on how often the IR uses image_placeholder/diagram_placeholder, and how well the template covers IR intents. |
| DROPPED | 4-6 (deck.audience, deck.throughline, deck.arc, deck.evidence_anchor, deck.duration_min) | Story-frame fields have no native pptx home. They're surfaced in the manifest so the speaker doesn't lose them. |
| ANNOTATED | 0 | Rare. |

A manifest with 0 DROPPED is suspicious — the IR's story-frame fields should always be DROPPED into the manifest, not silently absorbed.

A manifest with >10 LOSSY is a signal to revisit the template profile — likely missing layouts or weak style hierarchy.

## What this skill is NOT

- Not a visual polishing tool. The renderer reproduces structure + content. Visual fidelity is the template's job.
- Not a content generator. The IR is the source of truth for content; the renderer never invents.
- Not a chart engine. `metric` blocks render as typeset text; chart visualization is v0.3.
- Not a Figma renderer. See `render-figma`.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Composition with other skills

- **Upstream:** `story-compiler` produces the IR; `slide-ir-validator` validates it.
- **Pre-flight sibling:** `template-validator` ensures the profile's template is sound.
- **Loss-manifest semantics:** match the translation-engine convention so multi-format loss can be diffed.

## Reference

- Adapter: `adapters/pptx_renderer.py`.
- IR schema: `ir/schema.json`.
- Profile schema: `template-profile/schema.json`.
- Example IRs: `ir/examples/*.yaml`.
- python-pptx docs: <https://python-pptx.readthedocs.io>.
