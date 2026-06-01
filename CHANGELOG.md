# Changelog

All notable changes to slide-publisher are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v0.2

- Google Slides renderer (`render-gslides` + `template-extractor-gslides` + `template-synthesizer-gslides`).
- Transcript-mode and case-study-mode inputs for `story-compiler` (in addition to outline-mode).
- Synthesizer v2: shape embedding into the synthesized .pptx layouts; similarity-thresholded clustering for more forgiving pattern detection.
- Live structural checks for Figma in `template-validator` (`style_hierarchy`, `orphan_elements`-equivalent).
- Image asset copying in synthesizers.
- Loss-manifest diff tooling.

## [0.1.0] — pre-release

Initial release. Slice 1 covers the full pipeline: detection → extraction or synthesis → validation → IR compile → render to .pptx or Figma Slides → loss manifest.

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

### Known v0.1 limitations

- pptx synthesizer carries layout names + JSON-documented shape patterns; shape embedding into layouts is v0.2.
- Figma synthesizer is MCP-driven and requires Figma Desktop + an active file for end-to-end execution.
- Figma validator runs only 3 of 6 criteria; live structural checks deferred to v0.2.
- Renderer's body-block rendering concatenates blocks into the first body placeholder (v0.2 will allocate per-block when layouts support multiples).
- Bullet styling and metric-as-chart rendering deferred to v0.2.
- Clustering in both synthesizers is exact-match on quantized signature; similarity-thresholded clustering is v0.2.

[Unreleased]: https://github.com/designisagoodidea-2026/slide-publisher/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/designisagoodidea-2026/slide-publisher/releases/tag/v0.1.0
