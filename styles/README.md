# Storytelling styles

A named storytelling style is a complete configuration of arc choice, beat allocation, density rule, posture, and layout-intent priors. The compiler reads the user-selected style and shapes the IR accordingly.

## Why this exists

Authoritative voices agree on the principles (audience-as-hero, one idea per slide, visuals over paragraphs) but **disagree on density and posture**. Reynolds wants near-empty slides. Tufte wants dense data. McKinsey breaks both rules deliberately. An opinionated tool that picks one alienates the others. A *configurable* tool serves everyone.

## What ships in this folder

Eight starter styles representing the major schools of practice. Each is a plain YAML conforming to `schema.json`.

| File | School | Best for |
|---|---|---|
| `ted-talk.yaml` | Hero's Journey | Inspirational talks, founder pitches |
| `duarte-sparkline.yaml` | What-is/what-could-be contrast | Vision talks, persuasion decks |
| `reynolds-zen.yaml` | Presentation Zen — visual-heavy minimalism | Keynote-style spoken delivery |
| `tufte-data.yaml` | Show the data | Research readouts, analytical reviews |
| `mckinsey-pyramid.yaml` | Pyramid Principle | Executive briefings, consulting decks |
| `case-study-star.yaml` | Situation / Task / Action / Result | Interview answers, project readouts |
| `executive-briefing-provocation.yaml` | Provocation arc | Strategy decks, "we need to change" |
| `default-balanced.yaml` | Middle-of-the-road | When you don't know which to pick |

## Picking a style

```bash
cowork run story-from-outline --input my-talk.outline.md --style ted-talk --out my-talk.ir.yaml
```

Or set the style in the outline's frontmatter:

```yaml
---
style: tufte-data
audience: ...
throughline: ...
---
```

If neither is set, the compiler uses `default-balanced`.

## Authoring your own style

Copy a starter and modify. Save to:

```
~/.cowork/plugins/slide-publisher/styles/<your-style-name>.yaml
```

User styles override built-in styles of the same name. Validate against `schema.json` before saving:

```bash
cowork run storytelling-style-library --validate ~/.cowork/plugins/slide-publisher/styles/my-style.yaml
```

## Extending a built-in style

Use `extends:` to inherit from a parent style; your file's keys override parent keys:

```yaml
style_version: "1.0.0"
name: My TED variant
description: Like ted-talk but with more evidence slides.
extends: ted-talk

beats:
  evidence: {min: 3, max: 6, layout_intents: [quote, image_with_caption, metrics]}
```

Only the keys that differ need to appear.

## What a style does NOT control

- The IR schema (`ir/schema.json`) — styles produce IRs that conform to schema v1.
- Renderers, validators, remediators — those are template-side, not story-side.
- The user's template profile — styles influence which `layout_intent` the compiler picks per beat, but the renderer still uses the user's `layout_map` to resolve to concrete layouts.

## Versioning

Each style carries a `style_version` field. The compiler refuses to load a style with a major version mismatch. v1.x styles are forward-compatible within the v1 schema.
