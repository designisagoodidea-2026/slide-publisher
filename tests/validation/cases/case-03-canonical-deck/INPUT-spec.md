# Case 03 — Canonical deck-with-implicit-pattern

**Input.** `input.pptx` (copy of `tests/fixtures/synthetic-deck-no-template.pptx`).

**Represents.** A deck where every slide is hand-positioned content on the default Blank layout. The visual identity is in the SLIDES, not in any master/layout. 4 visual patterns × 2 slides = 8 slides.

**Tests.** The differentiator. If this case fails — classifier doesn't detect, synthesizer doesn't cluster, remediator doesn't act — the plugin's value-add is gone.

**Pipeline.** Classifier → Synthesizer → Extractor (on synthesized) → Validator → Remediator → Renderer.
