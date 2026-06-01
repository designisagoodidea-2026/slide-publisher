---
name: template-extractor-figma
description: Synthesize a slide-publisher template profile from a Figma file. Use this skill when the user supplies a Figma file key as part of the template-setup workflow — even when they say "build me a template from this Figma," "use this design system file," or "make this Figma work with slide-publisher." Drives the Figma MCP through the 8 Plugin API rules and post-processes results via adapters/template_extractor_figma.py.
---

# template-extractor-figma

Drive the Figma MCP to inspect a slide-template-rich Figma file, then post-process the result into a candidate template-profile entry. The skill encodes the Plugin API rules; the adapter does the normalization.

## When this skill triggers

- The user supplies a Figma file key during `template-setup` Step 3 (extraction).
- The user says "build a template from this Figma file" + provides a file key.
- The user has an existing Figma slide-template file and wants to validate it for slide-publisher.

Do NOT trigger when:

- The user has a `.pptx` — use `template-extractor-pptx` instead.
- The user has Google Slides — defer (v0.2).
- The Figma file is a finished deck (slides with content) rather than a template (named layouts ready to clone). Push back; templates are the input.

## Required inputs

1. **Figma file key.** Extract from the Figma URL: `figma.com/design/<file_key>/<filename>`.
2. **Figma MCP connected.** Run `cowork plugin grant slide-publisher --mcp figma` first. If not connected, refuse and surface the grant command.
3. **Figma Desktop app open** with the target file active. See Rule 7 below — browser-only sessions hit more timeouts. *(Inherited from cos-figma-publish-chain.)*

## The 8 Plugin API rules *(non-negotiable)*

Hard-won patterns from prior Figma MCP work. Violating any of them causes MCP timeouts.

### 1. Never use `findAll` on a slide

`slide.findAll(n => n.type === 'TEXT')` times out on any deck of meaningful size. The Plugin API does synchronous deep evaluation that compounds badly on Figma Slides structures. Use shallow navigation (Rule 3).

### 2. Identify templates by title text, not by slide name or page number

Slide names like `"34"` and page indices drift relative to actual content (reveal states, file reorganizations). The reliable signal is the title text inside each slide's Heading frame: `slide.children[0].children[0].characters`. Cache the result as the template map.

### 3. Use the shallow-navigation pattern

For a standard slide template:

```
SLIDE / FRAME
├── Heading (FRAME)
│   ├── Title (TEXT)
│   └── Body / subtitle (TEXT, optional)
├── Content frame 1..N (FRAME)
│   └── Content text (TEXT)
└── Visual (RECTANGLE / FRAME)
```

Reliable navigation paths:

- **Title:** `slide.children[0].children[0]`
- **Subtitle / body:** `slide.children[0].children[1]`
- **Content text per content frame N:** `slide.children[N].children[0].children[0]`

Document deviations in the extracted template map.

### 4. Pre-load fonts before reading or writing characters

```js
await figma.loadFontAsync({ family: "<family>", style: "Regular" });
await figma.loadFontAsync({ family: "<family>", style: "Bold" });
```

Don't try to read `node.fontName` first to discover the family — that often times out and isn't needed when you know it from the Figma text styles.

### 5. Restore styling after writing characters *(rendering rule — not used in extraction)*

(Documented here for symmetry with the publishing chain. Extractors don't write; they read.)

### 6. Verify by reading title text after every read

After fetching a template by node_id, read its title via the shallow path and confirm it matches what you expected to map. Catches template-ID drift early.

### 7. Use the Figma Desktop app, not the browser

The MCP performs noticeably better when Figma Desktop is open with the target file active. Browser-only sessions hit more timeouts.

### 8. Batch one Plugin API call per file inspection

Build a single Plugin API call that enumerates all slide templates, reads their titles, and pulls the color and text styles. Don't fragment into per-template calls — wasted overhead.

## Process — inspect → normalize → profile entry

### Step 1 — Drive the Figma MCP

Build one Plugin API call that produces the input the adapter expects:

```js
// Pseudocode — actual MCP tool name varies per Figma MCP install
async function inspectTemplate() {
  // 1. Enumerate top-level slide template frames
  const templates = [];
  const root = figma.root;
  for (const page of root.children) {
    for (const frame of page.children) {
      if (frame.type !== 'FRAME') continue;
      // Rule 3: shallow navigation
      const heading = frame.children?.[0];
      if (!heading) continue;
      const title = heading.children?.[0];
      if (!title || title.type !== 'TEXT') continue;
      templates.push({
        node_id: frame.id,
        title_text: title.characters,
      });
    }
  }

  // 2. Read color styles
  const colors = figma.getLocalPaintStyles().map(s => {
    const paint = s.paints[0];
    if (paint?.type !== 'SOLID') return null;
    const c = paint.color;
    const hex = '#' + [c.r, c.g, c.b]
      .map(v => Math.round(v * 255).toString(16).padStart(2, '0'))
      .join('');
    return { name: s.name, hex };
  }).filter(Boolean);

  // 3. Read text styles
  const texts = figma.getLocalTextStyles().map(s => ({
    name: s.name,
    family: s.fontName.family,
    size_pt: s.fontSize,
    weight: weightFromStyle(s.fontName.style),
    line_height: s.lineHeight?.value,
  }));

  return {
    file_key: figma.fileKey,
    slide_templates: templates,
    color_styles: colors,
    text_styles: texts,
  };
}
```

Output this JSON to a temp file (e.g., `/tmp/figma-inspect-<file_key>.json`).

### Step 2 — Pipe to the adapter

```bash
cd "<plugin-root>"
python adapters/template_extractor_figma.py /tmp/figma-inspect-<file_key>.json
```

The adapter normalizes the JSON into a slide-publisher template profile entry.

### Step 3 — Surface findings

Read `_findings` from the adapter output. Pass them through to `template-setup`'s quality report verbatim.

## Output shape

The adapter emits:

```json
{
  "file_key": "<key>",
  "layout_map": {
    "title": "1:1234",
    "section_break": "1:1238",
    ...
  },
  "template_map_json": "~/.cowork/plugins/slide-publisher/figma-<key>/template-map.json",
  "quality_score": 88,
  "style_tokens": {
    "colors": {
      "brand-primary": "#1F2A44",
      ...
    },
    "typography": {
      "display": {"family": "Söhne", "size_pt": 48, "weight": 700},
      ...
    }
  },
  "_inspected_templates": [
    {"node_id": "1:1234", "title_text": "Title Slide"},
    ...
  ],
  "_findings": [
    "All 10 IR layout intents have a matching Figma slide template.",
    ...
  ]
}
```

`file_key`, `layout_map`, `template_map_json`, and `quality_score` populate the template-profile schema's `templates.figma` branch. `style_tokens` populates the schema's top-level `style_tokens`. `_inspected_templates` and `_findings` are debug-only.

## When the heuristic doesn't fit

- **Title-text inference fails.** Templates with non-English or non-standard titles (e.g., "Mise en page") won't match the pattern dictionary. The user should add explicit layout-map overrides in `profile.yaml` after extraction.
- **No Figma color/text styles defined.** The file uses local color and text applications. Without named styles, the extractor can only enumerate templates — color and type tokens come back empty. Suggest the user define styles before re-running.
- **Multiple slide-template frames with the same title.** First match wins per layout intent. The remaining frames become orphans. Make sure each layout intent has exactly one canonical template.

## v0.1 limitations

- No automated structural validation (master fragmentation, orphan detection). The template-validator runs only `layout_catalog_completeness`, `color_tokens`, and `type_tokens` for Figma — see `template-validator/SKILL.md`.
- No auto-extraction of constraints / auto-layout properties. The renderer infers these at render time.
- Only one Figma file per profile. Multi-file design systems aren't supported in v0.1 — pick the primary slide template file.

## Anonymity (plugin policy)

This skill ships in the public, anonymous plugin. The adapter has no hard-coded organization patterns, no proprietary file references. The Plugin API rules are derived from generally-applicable Figma performance behavior, not from any specific user's deck-family.

The MCP call inspects the user's own Figma file; outputs reflect only that file's structure. No outbound network calls.

## Composition with other skills

- Called by `template-setup` Step 3 (extraction) when the user supplies a Figma source.
- Output feeds `template-validator` Step 4.
- Output's `template_map_json` path is honored by `render-figma` (Day 4) — the first render builds the cache; subsequent renders read it.

## What this skill is NOT

- Not the Figma renderer. Extraction is read-only inspection. Rendering happens in `render-figma`.
- Not a pptx extractor. The Figma path is structurally distinct (no python-pptx, MCP-driven).
- Not a Figma plugin author. The pseudocode in Step 1 is for the MCP runtime, not a standalone Figma plugin.

## Reference

- `adapters/template_extractor_figma.py` — the normalization adapter.
- `template-profile/schema.json` — the output structure.
- Figma Plugin API docs: <https://www.figma.com/plugin-docs/api/api-reference/>.
