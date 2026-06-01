# slide-publisher

> Story-aware slide generation across PowerPoint and Figma Slides. Compile your audience, throughline, and beats into a portable intermediate representation; render to multiple formats; get a named loss manifest with every render.

A Cowork plugin for people whose decks should reflect a structured story — not a stack of templates filled in. v0.1 supports `.pptx` and Figma Slides. Google Slides lands in v0.2.

## What makes this different

Most slide tooling assumes you bring a polished template. **In practice, most people don't have one.** They have a folder of decks that share a brand identity by author discipline, with no underlying master/layout structure to anchor a renderer to.

slide-publisher handles both cases. The plugin **classifies** the file you supply — is this a structured template, or a deck-with-implicit-pattern? — and routes accordingly:

- **Real template** → extract the layout catalog and style tokens directly.
- **Deck-with-implicit-pattern** → cluster the recurring visual patterns, synthesize a candidate template, then extract from that. The synthesized template is yours to refine or adopt as-is.
- **Mixed** → surface both options; you choose.

This detection + remediation is the differentiated piece. The rest of the plugin (story compiler, IR, renderers, loss manifests) sits on top.

## The pipeline

```
Your story (audience, throughline, beats, evidence)
        │
        ▼  [ story-compiler ]
        │
Deck IR (YAML, validated against ir/schema.json)
        │
        ▼  [ render-pptx ] or [ render-figma ]
        │   reads your template profile (per-user adapter)
        │
Rendered .pptx or Figma Slides + named loss manifest
```

The IR is the durable artifact. Renderers are commodity adapters per format. Every render produces a loss manifest naming what was preserved exactly, what was preserved with degradation, what was dropped, and what was annotated — so nothing is lost silently.

## Install

```bash
cowork plugin install slide-publisher
cowork plugin grant slide-publisher --mcp figma   # for Figma rendering
cowork run template-setup                         # one-time wizard
```

## First-run: the template-setup wizard

The wizard runs once, ingests your existing decks or templates, and produces a persistent template profile at `~/.cowork/plugins/slide-publisher/profile.yaml`. Subsequent renders read it transparently.

Seven steps:

1. **Discovery** — what do you have? Existing decks, an existing template, both, or starting fresh.
2. **Classification** — for each file you point at, the wizard runs `template-classifier`. Verdict: `template | deck-with-implicit-pattern | mixed`, plus the signals that drove the verdict (layout diversity ratio, default-layout fraction, semantic richness of layout names, etc.).
3. **Extraction or synthesis** — branches on the verdict. A real template goes straight to extraction; a deck-with-implicit-pattern goes through synthesis (cluster recurring patterns → derive layouts → emit a candidate template) and *then* extraction.
4. **Validation** — `template-validator` audits the candidate against six structural criteria (layout catalog completeness, style hierarchy, master usage, color tokens, type tokens, orphan elements) and produces green/yellow/red findings with concrete remediation per finding.
5. **Quality report** — you review the classifier diagnosis, the synthesizer's cluster summary (if invoked), and the validator findings together. Accept, iterate, or address findings in your source first.
6. **Preferred output** — pick a default render target.
7. **Persist** — the resulting profile lands in your config directory.

## After setup

Compile a story and render:

```bash
cowork run story-compiler --input my-talk.outline.md --out my-talk.ir.yaml
cowork run slide-ir-validator --strict my-talk.ir.yaml
cowork run render-pptx --ir my-talk.ir.yaml --out my-talk.pptx
cowork run render-figma --ir my-talk.ir.yaml
```

Both renderers read your profile automatically. Each emits the deck plus `my-talk.loss.md` + `my-talk.loss.json` alongside.

## Outline-mode contract

The story-compiler refuses to draft on missing audience, throughline, or evidence anchor. A deck without those is a deck without a point — the compiler asks instead of inventing.

A minimal outline:

```markdown
---
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
Enterprise pipeline has plateaued — four straight quarters flat at 8-10 deals.

## claim
Three reasons the middle market is the next motion: market shape, sales cycle, competitive window.

... [more beats] ...
```

See `ir/examples/` for three full generic examples used as renderer test fixtures.

## What's in the plugin

| Skill | Purpose |
|---|---|
| `story-compiler` | Outline-mode markdown → Deck IR YAML. Refuses on missing audience / throughline / evidence anchor. |
| `slide-ir-validator` | Validates an IR against the schema + 7 lint rules (missing speaker notes, layout/beat mismatch, throughline drift, etc.). |
| `template-setup` | The first-run wizard. Orchestrates the other template-* skills. |
| `template-classifier` | Detects whether a source is a template, a deck-with-implicit-pattern, or mixed. |
| `template-synthesizer-pptx` | Clusters recurring slide patterns into a synthesized .pptx template. |
| `template-synthesizer-figma` | Same, for Figma — drives the Figma MCP to create template frames in your file. |
| `template-extractor-pptx` | Inspects a real .pptx template and emits the profile entry. |
| `template-extractor-figma` | Same, for Figma. |
| `template-validator` | Six-criteria structural quality check with green/yellow/red findings. |
| `render-pptx` | IR + profile → .pptx + loss manifest. |
| `render-figma` | IR + profile → per-slide YAML the Figma MCP publishes. |

Each skill has its own SKILL.md under `skills/`. The Python adapters under `adapters/` do the heavy algorithmic work — clustering, extraction, validation, rendering — and the skills wrap them with usage context.

## Requirements

- Cowork `>= 0.x`
- Python `>= 3.10`
- `python-pptx`, `pyyaml`, `jsonschema` (installed automatically on plugin install)
- Figma MCP (user-supplied credentials) for Figma rendering

## Loss manifests

Every render produces a manifest in two formats:

- `<deck>.loss.md` — human-readable.
- `<deck>.loss.json` — machine-readable.

Categories:

- **LOSSLESS** — preserved exactly.
- **LOSSY** — preserved with degradation; the degradation is named.
- **DROPPED** — not preserved; reason captured.
- **ANNOTATED** — added by the renderer; not in the IR.

For a typical render through a well-fitting template, you'd expect ~1 + N lossless (deck title + per-slide content), 0-N lossy (layout substitutions, placeholder gaps), and 4-6 dropped (story-frame fields like `audience`, `throughline`, `arc` — preserved in the manifest only). A manifest with 0 dropped is suspicious; a manifest with >10 lossy suggests the template profile needs work. See `docs/LOSS-MANIFEST.md` for the full reference.

## Roadmap

- **v0.1** — pptx + Figma renderers, full template setup workflow with detection + remediation, outline-mode story compiler.
- **v0.2** — Google Slides renderer, transcript-mode and case-study-mode compilers, synthesizer v2 (shape embedding, similarity-thresholded clustering).
- **v0.3** — visual generation hooks (image placeholders resolved to AI-generated images via a separate image MCP).

## License

MIT. See `LICENSE`.
