# Case 01 — Well-formed pptx template

**Input.** `input.pptx` (copy of `tests/fixtures/synthetic-template.pptx`).

**Represents.** A pptx that should be classified as a real template: 10 layouts with semantically-rich IR-intent names, single master, sensible structure.

**Tests.** Baseline happy path. If this case fails, the entire pipeline is broken.

**Pipeline.** Classifier → Extractor → Validator → Renderer. Synthesizer and remediator should NOT trigger.
