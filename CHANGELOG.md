# Changelog

All notable changes to slide-publisher are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v0.3+

- Google Slides renderer (`render-gslides` + `template-extractor-gslides` + `template-synthesizer-gslides`).
- Synthesizer v2: shape embedding into the synthesized .pptx layouts; similarity-thresholded clustering.
- Image asset copying in synthesizers.
- Live structural checks for Figma in `template-validator` (`style_hierarchy`, `orphan_elements`-equivalent).
- Richer Figma Slides starter template (current minimal starter is task #100).

## [0.2.0] — 2026-06-02

Second release. Adds the storytelling layer (8 starter styles + 5 new compile-mode skills), the MCP-driven Figma template-instance path (extractor + renderer rewritten to drive the Anthropic-hosted Figma MCP rather than a user-installed plugin), the deterministic-preflight system (`CAPABILITIES.yaml` + `uat/preflight.py`), and the visual-QA routine (render harness + baselines + per-region diff + anomaly classifier + auto-remediation loop).

### Storytelling layer

- 8 starter style YAMLs in `styles/` matching real authorial frames — `ted-talk`, `duarte-sparkline`, `reynolds-zen`, `tufte-data`, `mckinsey-pyramid`, `case-study-star`, `executive-briefing-provocation`, `default-balanced`. JSON Schema 2020-12 validated. Inheritance via `extends:` field.
- 5 new compile-mode skills: `storytelling-style-library`, `story-from-outline`, `story-from-interview`, `story-from-transcript`, `story-from-deck`. Two pure-prose orchestrators (interview); three with backing adapters (transcript, deck, outline).
- New adapters: `style_loader.py` (resolves style chain with user-precedence override), `story_from_transcript.py` (claim-shape candidate extraction, beat segmentation, metric/quote scanning), `story_from_deck.py` (reverse-engineers IR from existing .pptx).

### MCP-driven Figma path

- `template-extractor-figma` rewrite — walk runs through Anthropic Figma MCP (`use_figma`); identifies slides by `sharedPluginData("slide_publisher", "intent")` rather than `slide.name` (Figma Slides auto-renumbers names). Probe lives at `skills/template-extractor-figma/probe.js`.
- `render-figma` Stage 2 — template-instance clone-and-populate pattern. Pre-loads fonts (Rule 4), walks template children shallowly (Rule 1), identifies TITLE/BODY by node name (Rule 6), `setCharacters` with style restore (Rule 5). Publish script at `skills/render-figma/stage2-publish.js`.
- No Figma Desktop install required. No user-installed plugin required. The MCP runs server-side.
- Starter Figma Slides template authored via MCP (10 named layouts matching IR-intent catalog).

### Deterministic preflight system

- `plugin/CAPABILITIES.yaml` — 48-entry manifest covering every skill, adapter, shared module, and architecture doc. Single source of truth for purposes, dependencies (binaries, MCPs, Python libs, internal), architecture-doc references, and UAT exposure state. The 27 `uat_exposed: no` entries make the visible debt explicit.
- `uat/preflight.py` — 8 checks: file existence, plugin.yaml coverage, UAT endpoint coverage, external binary detection, Figma architecture compliance, renderer loss-manifest compliance, visual regression gate, anonymity grep. Non-zero exit on any blocker.
- Project CLAUDE.md gained a *Consult-the-design-first rule* mandating Read SKILL.md → quote architecture → run preflight before any UAT change.

### Visual-QA routine

- Render harness at `tests/visual-qa/run_renders.py` — matrix over (IR × template × renderer), produces PNG outputs via LibreOffice + pdftoppm.
- Baselines manifest at `tests/visual-qa/baselines.yaml` + reference PNGs at `tests/visual-qa/baselines/` (`.gitignore`'d because LibreOffice tmp files carry host license info).
- `adapters/visual_diff.py` extended with per-region (title / body / footer) SSIM + pHash + mean-color delta + variance metrics.
- New `adapters/visual_anomaly_diagnose.py` — rules-based classifier with 5 v0.1 rules (title_overflow, missing_fill, empty_body, missing_decoration, font_substitution). Maps anomaly signatures to structured findings + recommended fixes + deterministic-fix flags.
- `adapters/iterate_to_parity.py` extended — auto-remediation loop applies deterministic fixes from the classifier (e.g., shorten IR title to fit) and re-renders. Falls back to v0.1 layout-swap if no deterministic fix applies.
- `uat/preflight.py check_visual_regression` BLOCKS on any SSIM regression below per-baseline threshold in the latest harness run. Warns on missing baselines.

### UAT wrapper

- v2-v6 iterations driven by user feedback during UAT:
  - v2: collapsed 6 plumbing steps to 3 user-facing actions (Your template / Your story / Generate); drag-and-drop .pptx upload.
  - v3: plain-English diagnosis + auto-fix button.
  - v4: hide all template-prep plumbing — server runs classify+extract+validate+remediate as one POST, UI shows one outcome card.
  - v5: Figma format toggle + Step 2 IR upload + slide preview.
  - v6: Figma toggle replaces raw-text stub with template-instance path. Server emits a chat-mediated publish payload; UI shows a copy-able command for the Claude session.

### Loss manifest

- `LossManifest` unified into `_common.py`. Per-renderer `extra` dict carries format-specific metadata (`template_path` for pptx, `file_key` for figma).

### Known v0.2 limitations

- Figma rendering requires the chat-mediated handoff (UAT server can't call MCP directly). Cowork integration in v0.3 will close this.
- Figma starter template is intentionally minimal — production-quality output requires either a richer starter (task #100) or a user-authored template following the slide-publisher labeling conventions.
- Visual-QA routine matrix doesn't include Figma renders (also chat-mediated).
- Body-block-to-text rendering differs slightly between pptx and figma renderers; centralizing in `_common.py` is task #98.
- Atlas-style fixed-bubble title placeholders cramp long IR titles; auto-detect + warn is task #99.

## [0.1.0] — 2026-06-01

Initial release. Slice 1 covers the full pipeline: detection → extraction or synthesis → validation → IR compile → render to .pptx or Figma Slides → loss manifest. **Externally validated against 12 templates we didn't design** (3 Microsoft built-in themes + 9 random web-sourced templates) — 12 of 12 validate as acceptable.

### Skills

- `story-compiler` — outline-mode markdown → Deck IR YAML. Refuses to draft on missing audience / throughline / evidence anchor.
- `slide-ir-validator` — schema validation + seven lint rules (missing speaker notes on key beats, layout/beat mismatch, throughline drift, missing transitions, evidence-anchor mismatch, beat ordering sanity, body-block fit). Default and `--strict` modes.
- `template-setup` — one-time install wizard orchestrating the other template-* skills.
- `template-classifier` — detects template / deck-with-implicit-pattern / mixed via weighted heuristic on layout diversity, default-layout ratio, direct-override count, and semantic richness of layout names. **The detection half of the differentiator.**
- `template-synthesizer-pptx` — cluster recurring slide patterns → derive canonical layouts → emit synthesized .pptx + JSON report. v0.1 carries layout names + token suggestions; shape embedding lands in v0.2.
- `template-synthesizer-figma` — MCP-driven counterpart. Walks slides via shallow navigation, clusters, creates new template frames in the user's file. **The remediation half of the differentiator.**
- `template-extractor-pptx` — inspect a real .pptx template, emit a profile entry.
- `template-extractor-figma` — same, for Figma (MCP-driven; the adapter normalizes the MCP output).
- `template-validator` — six-criteria structural quality check (layout catalog completeness, style hierarchy, master usage, color tokens, type tokens, orphan elements) with green/yellow/red findings + remediation per finding.
- `render-pptx` — IR + profile → .pptx + loss manifest. Layout fallback chain records every substitution.
- `render-figma` — IR + profile → per-slide YAML envelope for the Figma MCP publisher. Eight Plugin API rules encoded.

### Schemas

- `ir/schema.json` — Deck IR (JSON Schema 2020-12). Deck-level scaffolding (audience, throughline, arc, evidence anchor) + slide-level structure (beat, layout intent, body blocks, speaker notes, transitions). Ten layout intents, nine beats, six body-block kinds.
- `template-profile/schema.json` — per-user template profile. Per-format templates with layout maps and quality scores; style tokens (colors, typography, spacing); voice constraints pointer.

### Adapters

Eight Python adapters in `adapters/`:

- `template_classifier.py`, `template_synthesizer_pptx.py`, `template_synthesizer_figma.py`, `template_extractor_pptx.py`, `template_extractor_figma.py`, `template_validator.py`, `pptx_renderer.py`, `figma_yaml_emitter.py`.

### Fixtures

- `tests/fixtures/synthetic-template.pptx` — synthetic template with 10 IR-intent layouts.
- `tests/fixtures/synthetic-deck-no-template.pptx` — synthetic deck-with-implicit-pattern across 4 visual patterns × 2 slides.
- `tests/fixtures/synthetic-figma-mcp-output.json` — synthetic Figma MCP walk output for offline testing.
- `tests/integration/test_pipeline.py` — end-to-end integration test (classifier → synthesizer → extractor → validator → renderer; 13 assertions).

### Loss manifests

Every render emits both markdown (human-readable) and JSON (machine-readable) sidecars with four categories: LOSSLESS, LOSSY, DROPPED, ANNOTATED.

### Anonymity

The repo is anonymous open-source. No personally-identifying tokens anywhere in the artifact (enforced by `.githooks/pre-push`). The plugin neither bundles nor suggests any voice style; `voice_constraints` in the IR is an optional user-supplied pointer.

### External validation (added 2026-06-01)

The model was calibrated against industry-standard PowerPoint templates after the initial build to surface assumptions that didn't match real-world practice. Findings and fixes:

- **`layout_catalog_completeness`** — required 10/10 IR intents to match by layout name. Microsoft templates carry 5 structural matches. Fixed: use *effective coverage* (direct match + documented fallback chain). Templates that map `claim_with_evidence` cleanly now count `three_pillars`, `metrics`, etc. as covered.
- **`style_hierarchy` + `color_tokens`** — only inspected slide-master XML. Industry templates carry colors and fonts in `ppt/theme/theme1.xml` (`clrScheme`, `fontScheme`). Fixed: read theme XML and credit both paths.
- **Classifier signals** — treated canonical Office layout names ("Title Slide", "Title and Content") as "stock = bad" signal. Those names ARE the canonical names good templates use. Fixed: removed Office canonical names from the bad-signal set; added low-slide-count branch that weights layout-catalog signals over slide-usage signals.
- **`orphan_elements`** — flagged 90%+ unused layouts as red. Rich-catalog templates legitimately have many specialized layouts. Fixed: relaxed thresholds (red at 95% unused, yellow at 85%).
- **`.ppt` legacy conversion** — LibreOffice's `--convert-to pptx` filter is structurally lossy; converted files lose their layout catalog. Documented as a v0.2 item — `input-ppt` should warn users and recommend re-saving in PowerPoint instead.

After-fix results: 7 pass + 2 warn out of 9 native .pptx files (excluding a PowerPoint lock file). All 3 Microsoft built-in themes pass.

### Known v0.1 limitations

- pptx synthesizer carries layout names + JSON-documented shape patterns; shape embedding into layouts is v0.2.
- Figma synthesizer is MCP-driven and requires Figma Desktop + an active file for end-to-end execution.
- Figma validator runs only 3 of 6 criteria; live structural checks deferred to v0.2.
- Renderer's body-block rendering concatenates blocks into the first body placeholder (v0.2 will allocate per-block when layouts support multiples).
- Bullet styling and metric-as-chart rendering deferred to v0.2.
- Clustering in both synthesizers is exact-match on quantized signature; similarity-thresholded clustering is v0.2.

[Unreleased]: https://github.com/designisagoodidea-2026/slide-publisher/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/designisagoodidea-2026/slide-publisher/releases/tag/v0.2.0
[0.1.0]: https://github.com/designisagoodidea-2026/slide-publisher/releases/tag/v0.1.0
