# slide-publisher

> Story-aware slide generation across PowerPoint and Figma Slides. Compile your audience, throughline, and beats into a portable intermediate representation; render to multiple formats; get a named loss manifest with every render.

A Cowork plugin for people whose decks should reflect a structured story — not a stack of templates filled in. **v0.2 is live.** PowerPoint + Figma Slides are supported targets; Google Slides lands in v0.3.

## What's in v0.2

Compared to v0.1, the plugin gains four substantial systems:

- **Storytelling layer.** 8 starter styles (`ted-talk`, `duarte-sparkline`, `reynolds-zen`, `tufte-data`, `mckinsey-pyramid`, `case-study-star`, `executive-briefing-provocation`, `default-balanced`) + 5 compile-mode skills (`storytelling-style-library`, `story-from-outline`, `story-from-interview`, `story-from-transcript`, `story-from-deck`). Pick a style; bring your own outline, interview transcript, raw transcript, or even an existing deck to reverse-engineer into IR.
- **MCP-driven Figma template-instance path.** No Figma Desktop install needed. No user-installed plugin. The extractor + Stage 2 renderer drive the Anthropic Figma MCP directly — clone named layout slides, populate via `setCharacters`, restore styling per the 8 Plugin API rules. Output is a real Figma Slides file you open in your browser.
- **Deterministic preflight.** `CAPABILITIES.yaml` is the single source of truth for every skill, adapter, shared module, and architecture doc (49 entries). `uat/preflight.py` runs 8 checks (file existence, manifest coverage, UAT endpoint coverage, external binary detection, Figma architecture compliance, renderer loss-manifest compliance, visual regression gate, anonymity grep). Non-zero exit on any blocker. Stops architecture drift mechanically, not by trying harder.
- **Visual-QA routine.** Continuous regression detection + auto-improvement. `tests/visual-qa/run_renders.py` matrix harness × baseline manifest × per-region SSIM diff × rules-based anomaly classifier × auto-remediation loop. Preflight BLOCKS on SSIM drift below baseline threshold. Built because correctness of visual artifacts can only be verified visually.

## What makes this different

Most slide tooling assumes you bring a polished template. **In practice, most people don't have one.** They have a folder of decks that share a brand identity by author discipline, with no underlying master/layout structure to anchor a renderer to. Slide-publisher handles both cases.

**Validated against 12 templates we didn't design.** The model was calibrated against 3 Microsoft built-in themes + 9 random web-sourced PowerPoint templates (military, medical, academic, university, corporate). 12 of 12 native .pptx templates validate as acceptable. See `docs/VALIDATION.md` for the methodology.

The plugin **classifies** the file you supply — is this a structured template, or a deck-with-implicit-pattern? — and routes accordingly:

- **Real template** → extract the layout catalog and style tokens directly.
- **Deck-with-implicit-pattern** → cluster the recurring visual patterns, synthesize a candidate template, then extract from that. The synthesized template is yours to refine or adopt as-is.
- **Mixed** → surface both options; you choose.

This detection + remediation is the differentiated piece. The rest of the plugin (story compiler, IR, renderers, loss manifests) sits on top.

## The pipeline

```
Your story (audience, throughline, beats, evidence)
        │
        ▼  [ story-compiler ] or one of:
        │     [ story-from-outline | story-from-interview |
        │       story-from-transcript | story-from-deck ]
        │
        ▼  [ storytelling-style-library ] — optional style overlay
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
2. **Classification** — for each file you point at, the wizard runs `template-classifier`. Verdict: `template | deck-with-implicit-pattern | mixed`, plus the signals that drove the verdict.
3. **Extraction or synthesis** — branches on the verdict. A real template goes straight to extraction; a deck-with-implicit-pattern goes through synthesis (cluster recurring patterns → derive layouts → emit a candidate template) and *then* extraction.
4. **Validation** — `template-validator` audits the candidate against six structural criteria with green/yellow/red findings + concrete remediation per finding.
5. **Quality report** — you review the classifier diagnosis, the synthesizer's cluster summary (if invoked), and the validator findings together. Accept, iterate, or address findings in your source first. **If the verdict is `fail`, auto-remediation (`remediation-apply-pptx` / `remediation-apply-figma`) applies deterministic fixes (layout renames, theme alignment) and re-validates.**
6. **Preferred output** — pick a default render target.
7. **Persist** — the resulting profile lands in your config directory.

## Bring your own story shape

Beyond outline-mode, v0.2 adds four compile entry points so you don't have to write a markdown outline before you have a deck:

- `story-from-outline` — the classic path; the compiler refuses to draft on missing audience / throughline / evidence anchor.
- `story-from-interview` — conversational. The skill asks you the questions a structured interview would, builds the IR as you answer.
- `story-from-transcript` — point it at a recorded talk transcript; the adapter surfaces throughline candidates, beat segments, metrics, and quotes for you to pick from.
- `story-from-deck` — reverse-engineers an IR from an existing `.pptx`. Useful when the deck already exists and you want the durable story artifact.

Apply a style on top of any of these via `storytelling-style-library`. Or skip styles and let the renderer use defaults.

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
```

See `ir/examples/` for three full generic examples used as renderer test fixtures.

## What's in the plugin

| Skill | Purpose |
|---|---|
| `story-compiler` | Outline-mode markdown → Deck IR YAML. Refuses on missing audience / throughline / evidence anchor. |
| `slide-ir-validator` | Validates an IR against the schema + 7 lint rules. |
| `template-setup` | The first-run wizard. Orchestrates the other template-* skills. |
| `template-classifier` | Detects whether a source is a template, a deck-with-implicit-pattern, or mixed. |
| `template-synthesizer-pptx` | Clusters recurring slide patterns into a synthesized .pptx template. |
| `template-synthesizer-figma` | Same, for Figma — drives the MCP to create template frames in your file. |
| `template-extractor-pptx` | Inspects a real .pptx template and emits the profile entry. |
| `template-extractor-figma` | Walks a Figma Slides template via MCP; identifies slides by shared plugin data. |
| `template-validator` | Six-criteria structural quality check with green/yellow/red findings. |
| `remediation-apply-pptx` | Auto-fix a failing .pptx template (layout rename + recommendations). |
| `remediation-apply-figma` | Auto-fix a failing Figma template via MCP. |
| `render-pptx` | IR + profile → .pptx + loss manifest. |
| `render-figma` | IR + profile → Figma Slides file via MCP template-instance pattern. |
| `input-pdf` / `input-png` / `input-ppt` | Accept additional source formats. Legacy `.ppt` converted via LibreOffice. |
| `visual-diff` / `iterate-to-parity` | Per-region SSIM + auto-remediation loop. |
| `storytelling-style-library` | 8 starter styles + user-style precedence + `extends:` chain resolution. |
| `story-from-outline` / `story-from-interview` / `story-from-transcript` / `story-from-deck` | Alternative compile entry points. |
| `visual-qa-routine` | Continuous regression detection + auto-improvement. |

Each skill has its own SKILL.md under `skills/`. The Python adapters under `adapters/` do the heavy algorithmic work; the skills wrap them with usage context. `plugin/CAPABILITIES.yaml` is the authoritative manifest covering every skill + adapter + shared module + doc.

## Requirements

- Cowork `>= 0.x`
- Python `>= 3.10`
- `python-pptx`, `pyyaml`, `jsonschema` (installed automatically on plugin install)
- LibreOffice (only for `.ppt` legacy conversion via `input-ppt`)
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

- **v0.1** ✓ — pptx + Figma renderers, full template setup workflow with detection + remediation, outline-mode story compiler. Externally validated against 12 templates we didn't design.
- **v0.2** ✓ — storytelling layer (8 styles + 5 compile-mode skills), MCP-driven Figma template-instance path (no Desktop / no user plugin), deterministic preflight system, visual-QA routine.
- **v0.3** — Google Slides renderer; richer Figma Slides starter template with brand styling; image-placeholder resolution via image MCPs.

## License

MIT. See `LICENSE`.
