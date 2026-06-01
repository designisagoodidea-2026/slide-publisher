# slide-publisher

> **Status: pre-v0.1.** Schemas locked; renderers and skills land before tagged release.

A Cowork plugin that compiles a story (audience, throughline, beats, evidence) into a portable slide IR, then renders to PowerPoint or Figma Slides. Google Slides lands in v0.2.

## What it does

`slide-publisher` separates a deck into three layers:

1. **Story** — what you want the audience to leave with. Audience, throughline, beats, evidence anchor.
2. **IR** — a structured, validated YAML representation of the deck. Beat-and-layout-intent per slide, body blocks, speaker notes, transitions. The IR is the durable artifact.
3. **Rendered deck** — `.pptx` or Figma Slides, populated through a per-user **template profile** that maps generic IR to your brand-consistent template. Each render emits a loss manifest naming what's lossless, lossy, dropped, or annotated.

Treating story-to-slide as a translation across heterogeneous targets, with a named loss surface, is the doctrinal pattern this plugin instantiates.

## Install

```
cowork plugin install slide-publisher
cowork plugin grant slide-publisher --mcp figma
cowork run template-setup
```

The `template-setup` wizard is a one-time install workflow:

1. **Discovery** — existing decks, existing templates, both, or starting fresh?
2. **Classification** — for each source, is it already a template or a loose deck?
3. **Extraction** — loose decks get synthesized into a candidate template you review.
4. **Validation** — existing templates run through a structural quality check (layout-catalog completeness, style hierarchy, master usage, color tokens, type tokens, orphan elements) with green/yellow/red findings + remediation.
5. **Quality report** — accept the template as-is or address findings first.
6. **Preferred output** — pick a default render target (pptx or Figma in v0.1).
7. **Persist** — the resulting `profile.yaml` lands at `~/.cowork/plugins/slide-publisher/profile.yaml`.

## Use

```
cowork run story-compiler --input my-talk.outline.md --out my-talk.ir.yaml
cowork run render-pptx     --ir my-talk.ir.yaml --out my-talk.pptx
cowork run render-figma    --ir my-talk.ir.yaml
```

Both renderers read your template profile automatically. Each emits a loss manifest (`my-talk.loss.md` + `my-talk.loss.json`) alongside the output deck.

## Requirements

- Cowork `>= 0.x`
- Python `>= 3.10`
- Figma MCP (user-supplied credentials)

## License

MIT. See `LICENSE`.
