---
name: render-figma
description: Render a validated Deck IR into Figma Slides via the Figma MCP, using the user's template profile. Emits the per-slide YAML the publisher consumes plus a markdown loss manifest and JSON sidecar. Use this skill whenever the user wants Figma Slides as output — "render to Figma," "publish to my Figma file," "build the slides in Figma," or when their preferred_output is figma and they've just compiled an IR.
---

# render-figma

Two-stage rendering: (1) the adapter translates IR + profile into per-slide YAML; (2) the skill drives the Figma MCP to clone templates and populate content. The 8 Plugin API rules apply to stage 2.

## When this skill triggers

- The user says "render to Figma," "publish to my Figma file," "make the slides in Figma."
- A story-compiler invocation completed and the user's `preferred_output` in their profile is `figma`.
- A render-pptx call hit an error and the user wants to try the other format.

## Architecture

```
IR YAML + profile.yaml
        │
        ▼
[ figma_yaml_emitter.py ]  ← pure transformation, testable offline
        │
        ▼
per-slide YAML envelope + loss manifest (md + json)
        │
        ▼
[ Figma MCP — invoked from this skill ]  ← 8 Plugin API rules apply
        │
        ▼
Slides populated in the user's Figma file
        │
        ▼
slide-id-map.json sidecar (cached for future renders)
```

The adapter is pure Python — no MCP dependency. The skill is the MCP driver — describes the Plugin API patterns and post-render verification.

## Pre-flight

Same as render-pptx:

1. IR is schema-valid (`slide-ir-validator --strict`).
2. Template profile is structurally valid (`template-validator --strict --format figma`).
3. **Figma MCP connected.** Run `cowork plugin grant slide-publisher --mcp figma` if not.
4. **Figma Desktop app open** with the target file active. *(Rule 7 — browser-only sessions hit more timeouts.)*

## Stage 1 — Emit per-slide YAML

```bash
cd "<plugin-root>"
python adapters/figma_yaml_emitter.py \
  --ir /path/to/deck.ir.yaml \
  --profile ~/.cowork/plugins/slide-publisher/profile.yaml \
  --out /path/to/deck.figma.yaml
```

Outputs:

- `deck.figma.yaml` — per-slide YAML envelope (consumed in Stage 2).
- `deck.figma.yaml.loss.md` — markdown loss manifest (Stage 1 only; Stage 2 may add to it).
- `deck.figma.yaml.loss.json` — JSON sidecar.

The envelope shape:

```yaml
deck_title: <string>
file_key: <Figma file key>
slides:
  - slide_id: <kebab-case>
    template_node_id: <Figma node id of the template to clone>
    title: <string>
    body:
      - kind: prose | bullets | metric | quote | image_caption | diagram_caption
        text: <string | list | dict, depending on kind>
    speaker_notes: <string>           # optional
```

## Stage 2 — Drive the Figma MCP

This stage uses the Figma MCP. The 8 Plugin API rules apply.

### The 8 rules

1. **Never use `findAll` on a slide.** Times out at scale. Use the shallow navigation in Rule 3.
2. **Identify templates by title text, not by slide name or page number.** Slide names and indices drift. Title text inside the Heading frame is the reliable signal. The emitter already provides `template_node_id` per slide so this stage can clone by ID directly.
3. **Use the shallow-navigation pattern.** Standard slide structure:
   ```
   SLIDE / FRAME
   ├── Heading (FRAME)
   │   ├── Title (TEXT)
   │   └── Body / subtitle (TEXT, optional)
   ├── Content frame 1..N (FRAME)
   │   └── Content text (TEXT)
   └── Visual (RECTANGLE / FRAME)
   ```
   Navigation paths:
   - Title: `slide.children[0].children[0]`
   - Body/subtitle: `slide.children[0].children[1]`
   - Content text for content frame N: `slide.children[N].children[0].children[0]`
4. **Pre-load fonts.** Before any `setCharacters`, call `figma.loadFontAsync({family, style})` for every (family, style) pair the slide uses.
5. **Restore styling after `setCharacters`.** `node.characters = "..."` collapses character-range styling. Restore bold-headline + regular-body via `setRangeFontName(start, end, {family, style})`. For bulleted lists, use `setRangeListOptions(start, end, {type: "UNORDERED"})` or prefix with `"• "`.
6. **Verify by reading title text after every clone.** Cheap drift detection. If the clone's title doesn't match the expected layout title, log the mismatch and reroute or stop.
7. **Use Figma Desktop, not the browser.** MCP performs noticeably better.
8. **Batch one Plugin API call per deck.** Once you have the template-map cache and clone IDs, all text replacements for a single deck fit in one Plugin API call. Don't fragment per-slide.

### Sequence

1. **Load the template-map cache.** Read `templates.figma.template_map_json` from the profile. If it doesn't exist yet, build it during the first render and persist for future runs.
2. **Pre-load fonts.** Walk the profile's `style_tokens.typography` and call `loadFontAsync` for each (family, style) pair.
3. **Clone templates.** For each slide in the envelope, clone `template_node_id` into the active SLIDE_ROW. Append in IR order; Figma's auto-positioning handles grid placement.
4. **Verify clones.** For each clone, read `slide.children[0].children[0].characters` (Rule 3) and confirm it matches what the template's title was meant to be. Log drift to the loss manifest.
5. **Populate text content.** Per slide:
   - Set title at `slide.children[0].children[0]`.
   - Set body content at `slide.children[N].children[0].children[0]` for each body block. Use Rule 5 styling restoration.
6. **Set speaker notes.** Per slide, apply `speaker_notes` to the slide's notes field (if Figma Slides supports it via MCP in your install).
7. **Emit a slide-id-map.json sidecar** at `<deck-folder>/<deck>-slide-id-map.json`:
   ```json
   {
     "deck_title": "...",
     "file_key": "...",
     "rendered_at": "...",
     "slide_ids": {
       "<ir-slide-id>": "<figma-node-id-of-clone>",
       ...
     }
   }
   ```
   This is what allows downstream tooling to know which Figma node ID corresponds to which IR slide.

### Stage-2 additions to the loss manifest

The adapter emits a loss manifest in Stage 1. After Stage 2, append:

- LOSSY entries per clone-verification mismatch (Rule 6).
- LOSSY entries per styling restoration that couldn't fully recover (e.g., character-range italic that wasn't in the IR).
- ANNOTATED entries for nodes the publisher adds (e.g., a "Continued" marker on overflow).

## Loss-manifest categories

Same convention as render-pptx and the translation-engine manifests:

- **LOSSLESS** — preserved exactly.
- **LOSSY** — preserved with degradation.
- **DROPPED** — not preserved; reason captured.
- **ANNOTATED** — added by renderer.

For a typical IR + well-fitting Figma template, expect:

| Category | Typical count | Why |
|---|---|---|
| LOSSLESS | ~slide count + 1 | Title, body, speaker notes per slide; deck title preserved as batch label. |
| LOSSY | 0-N | Layout substitutions when intents are missing from the layout_map; clone-verification drift. |
| DROPPED | 4-6 (deck-level) | Story-frame fields with no native Figma representation. |
| ANNOTATED | 0-N | image_placeholder / diagram_placeholder emitted as alt+intent captions; publisher annotations. |

## What this skill is NOT

- Not a Figma plugin author. Stage 2 invokes the Figma MCP tools available in the user's Cowork session — it does not author or install plugins.
- Not a content generator. The IR is the source of truth.
- Not the figma-extractor. See `template-extractor-figma` for inspection.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Composition with other skills

- **Upstream:** `story-compiler` produces the IR; `slide-ir-validator` validates it; `template-validator` confirms the profile's Figma template is sound.
- **Sibling renderer:** `render-pptx` is the pptx equivalent.

## Reference

- Adapter: `adapters/figma_yaml_emitter.py`.
- IR schema: `ir/schema.json`.
- Profile schema: `template-profile/schema.json` (especially the `templates.figma` branch).
- Figma Plugin API: <https://www.figma.com/plugin-docs/api/api-reference/>.
