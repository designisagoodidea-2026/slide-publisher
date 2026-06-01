# Figma Plugin API rules

Hard-won patterns for working with the Figma MCP / Plugin API. Violating any of these causes timeouts at scale. Referenced from every Figma-touching skill in the plugin.

## The 8 rules

### 1. Never use `findAll` on a slide

`slide.findAll(n => n.type === 'TEXT')` times out on any deck of meaningful size. The Plugin API does synchronous deep evaluation that compounds badly on Figma Slides structures. Use shallow navigation (Rule 3).

### 2. Identify templates by title text, not by slide name or page number

Slide names (e.g., `"34"`) and page indices drift relative to actual content (reveal-state slides, deck reorganizations). The reliable signal is the title text inside each slide's Heading frame: `slide.children[0].children[0].characters`. Cache the result in a template-map sidecar.

### 3. Use the shallow-navigation pattern

Standard slide structure:

```
SLIDE / FRAME
├── Heading (FRAME)
│   ├── Title (TEXT)
│   └── Body/subtitle (TEXT, optional)
├── Content frame 1..N (FRAME)
│   └── Content text (TEXT)
└── Visual (RECTANGLE / FRAME)
```

Navigation paths:

- **Title:** `slide.children[0].children[0]`
- **Body / subtitle:** `slide.children[0].children[1]`
- **Content text per frame N:** `slide.children[N].children[0].children[0]`

Document deviations in the template map.

### 4. Pre-load fonts before reading or writing characters

```js
await figma.loadFontAsync({ family: "<family>", style: "Regular" });
await figma.loadFontAsync({ family: "<family>", style: "Bold" });
```

Don't try to read `node.fontName` first to discover the family — that often times out and isn't needed when you know it from the file's text styles.

### 5. Restore styling after `setCharacters`

`node.characters = "..."` collapses character-range styling to the first character's font. Restore:

```js
node.setRangeFontName(0, headlineLen, { family: "<family>", style: "Bold" });
node.setRangeFontName(headlineLen + 1, totalLen, { family: "<family>", style: "Regular" });
```

For bulleted lists: `node.setRangeListOptions(start, end, { type: "UNORDERED" })`. Fallback: prefix with `"• "`.

### 6. Verify by reading title text immediately after every clone

After every clone or rename, read the title via the shallow path and confirm it matches the expected layout. Cheap drift detection now; expensive after writing all content.

### 7. Use the Figma Desktop app, not the browser

The MCP performs noticeably better when Figma Desktop is open with the target file active. Browser-only sessions hit more timeouts.

### 8. Batch one Plugin API call per operation

Once you have node IDs cached, all reads or writes for a single operation (one extraction, one synthesis pass, one remediation pass) fit in one Plugin API call. Don't fragment per-node.

## Where these rules apply

- `template-extractor-figma` — Stage 1 walk.
- `template-synthesizer-figma` — Stages 1 (walk) and 3 (frame creation).
- `template-validator` (figma path) — only when running live structural checks (v0.2).
- `remediation-apply-figma` — Stage 2 execution.
- `render-figma` — Stage 2 publishing.
