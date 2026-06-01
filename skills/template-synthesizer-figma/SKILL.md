---
name: template-synthesizer-figma
description: Synthesize a Figma template from a deck-with-implicit-pattern Figma file. Use this skill whenever the template-classifier verdict is "deck-with-implicit-pattern" for a Figma source. Drives the Figma MCP through a two-stage pipeline (walk source slides → cluster + plan via the adapter → create new template frames in the user's file). Also use when the user says "build a Figma template from this file," "extract template patterns from this Figma deck."
---

# template-synthesizer-figma

The Figma counterpart to `template-synthesizer-pptx`. Detects recurring visual patterns in a loose Figma deck and creates new template frames in the user's file. The 8 Plugin API rules apply throughout.

## When this skill triggers

- `template-classifier` returns `deck-with-implicit-pattern` for a Figma source.
- The user explicitly asks "build a template from this Figma file" or "derive templates."

## Architecture

```
Figma file (loose deck)
        │
        ▼  [Stage 1] MCP Plugin API call — walk slides, gather shape signatures
        │
JSON: slides with shape geometry, fonts, fills
        │
        ▼  [Stage 2] adapters/template_synthesizer_figma.py
        │
JSON: clusters + suggested_layout_map + tokens + mcp_creation_plan
        │
        ▼  [Stage 3] MCP Plugin API call — create new template frames
        │
Figma file now has a "Templates" page with N new template frames
        │
        ▼
template-extractor-figma → profile entry → user review → profile.yaml lock
```

The adapter is pure Python (testable offline). The two Figma MCP stages bracket it; the SKILL.md describes both.

## Pre-flight

1. **Figma MCP connected.** `cowork plugin grant slide-publisher --mcp figma` if not.
2. **Figma Desktop app open** with the target file active (Rule 7).
3. **User confirmation.** This skill **writes to the user's file**. Ask before proceeding: "I'll create a new page named 'Templates (synthesized by slide-publisher)' in your file with N synthesized template frames. Proceed?" Wait for explicit yes.

## Stage 1 — Walk the source slides

Use the Figma MCP to gather shape data per slide. Apply the shallow-navigation pattern (Rule 3) — never `findAll` (Rule 1).

```js
async function walkSlides() {
  const slides = [];
  // Slides are top-level FRAMEs in the slide deck file
  for (const page of figma.root.children) {
    for (const node of page.children) {
      if (node.type !== 'FRAME') continue;
      const slide = {
        slide_id: node.id,
        shapes: [],
      };
      // Walk one level deep; record shape geometry + font + fill
      for (const child of node.children) {
        slide.shapes.push({
          kind: classifyKind(child),
          x: child.x, y: child.y,
          width: child.width, height: child.height,
          text: child.type === 'TEXT' ? child.characters : null,
          font_family: child.type === 'TEXT' ? child.fontName?.family : null,
          font_size_pt: child.type === 'TEXT' ? child.fontSize : null,
          font_weight: child.type === 'TEXT' ? weightFromStyle(child.fontName?.style) : null,
          fill_hex: extractFillHex(child),
        });
      }
      slides.push(slide);
    }
  }
  return {
    file_key: figma.fileKey,
    slides,
    existing_styles: {
      colors: figma.getLocalPaintStyles().map(s => ({
        name: s.name,
        hex: paintToHex(s.paints[0]),
      })),
      text: figma.getLocalTextStyles().map(s => ({
        name: s.name,
        family: s.fontName.family,
        size_pt: s.fontSize,
        weight: weightFromStyle(s.fontName.style),
      })),
    },
  };
}
```

Write the result to `/tmp/figma-walk-<file_key>.json`.

## Stage 2 — Run the adapter

```bash
cd "<plugin-root>"
python adapters/template_synthesizer_figma.py /tmp/figma-walk-<file_key>.json \
  --out /tmp/synthesis-plan-<file_key>.json
```

The adapter clusters the slides, derives layout names + intents, extracts tokens, and produces an `mcp_creation_plan` ready for Stage 3.

## Stage 3 — Create the template frames

Drive the MCP to execute the creation plan. One Plugin API call per the batch rule (Rule 8).

```js
async function createTemplates(plan) {
  // Pre-load every font the plan uses (Rule 4)
  const fonts = new Set();
  for (const frame of plan.frames_to_create) {
    for (const child of frame.children) {
      if (child.type === 'TEXT') {
        fonts.add(JSON.stringify({
          family: child.font.family,
          style: weightToStyle(child.font.weight),
        }));
      }
    }
  }
  for (const fontJson of fonts) {
    await figma.loadFontAsync(JSON.parse(fontJson));
  }

  // Create the Templates page
  const page = figma.createPage();
  page.name = plan.templates_page_name;

  // Create one FRAME per cluster
  for (const frameSpec of plan.frames_to_create) {
    const frame = figma.createFrame();
    frame.name = frameSpec.name;
    frame.resize(plan.frame_size.width, plan.frame_size.height);
    page.appendChild(frame);

    for (const child of frameSpec.children) {
      if (child.type === 'TEXT') {
        const text = figma.createText();
        text.fontName = {
          family: child.font.family,
          style: weightToStyle(child.font.weight),
        };
        text.fontSize = child.font.size_pt;
        text.characters = child.placeholder_text;
        text.x = child.x;
        text.y = child.y;
        text.resize(child.width, child.height);
        if (child.fill_hex) {
          text.fills = [{ type: 'SOLID', color: hexToRgb(child.fill_hex) }];
        }
        frame.appendChild(text);
      } else if (child.type === 'RECTANGLE') {
        const rect = figma.createRectangle();
        rect.name = child.name;
        rect.x = child.x;
        rect.y = child.y;
        rect.resize(child.width, child.height);
        rect.fills = [{ type: 'SOLID', color: { r: 0.9, g: 0.9, b: 0.9 } }];
        frame.appendChild(rect);
      }
    }

    // Verify the title was created correctly (Rule 6)
    const titleNode = frame.children[0];
    if (titleNode && titleNode.type === 'TEXT') {
      // Log to confirm position match — extends to loss manifest if needed
    }
  }
}
```

## After Stage 3

1. Run `template-extractor-figma` against the user's file. It should now find the new template frames on the "Templates" page.
2. Run `template-validator` against the resulting profile.
3. Surface the cluster summary + validator findings to the user. Ask: "Adopt this as your template? [y / iterate / cancel]"
4. On yes: persist the file_key + suggested layout_map + tokens to `profile.yaml`.

## v0.1 limitations

- **Adapter does no MCP work.** The clustering algorithm runs offline. The two MCP stages are runtime steps in the user's Cowork session. The skill orchestrates; the adapter computes.
- **Exact-match clustering** — same limitation as `template-synthesizer-pptx`.
- **Placeholder text only.** Synthesized text frames carry `{{ Title }}`, `{{ Body Text }}` style placeholders. The user replaces them at render time via `render-figma`.
- **No image asset copying.** Image shapes in the source become gray rectangles in the synthesized templates. The user adds real images post-synthesis.
- **No constraint or auto-layout setup.** Synthesized frames use fixed positions. v0.2 will infer Figma constraints/auto-layout from the source patterns.

## What this skill is NOT

- Not a Figma renderer. See `render-figma`.
- Not a pptx synthesizer. See `template-synthesizer-pptx`.
- Not a layout designer. The synthesizer detects existing patterns; it doesn't invent layouts the source doesn't exhibit.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Composition with other skills

- **Upstream:** `template-classifier` gates invocation (Figma `deck-with-implicit-pattern` verdict).
- **Sibling:** `template-extractor-figma` runs on the user's file after synthesis to produce the profile entry.
- **Downstream:** `render-figma` consumes the profile.

## Reference

- Adapter: `adapters/template_synthesizer_figma.py`.
- Plugin API rules: see `template-extractor-figma/SKILL.md` § "The 8 Plugin API rules."
- IR layout-intent catalog: `ir/schema.json` § `layout_intent` enum.
