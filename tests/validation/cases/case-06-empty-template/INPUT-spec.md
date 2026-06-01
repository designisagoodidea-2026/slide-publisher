# Case 06 — Empty template

**Input.** `input.pptx` — masters + default layouts, but no slides.

**Tests.** Graceful corner-case handling. The classifier currently surfaces a clear "no slides" diagnosis; the extractor should still produce a profile from the layouts.

**Pipeline.** Classifier → Extractor → Validator.
