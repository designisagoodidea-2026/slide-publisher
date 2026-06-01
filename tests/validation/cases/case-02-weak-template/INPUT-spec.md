# Case 02 — Weak template

**Input.** `input.pptx` — generic-named layouts (`Layout A` through `Layout D`), no defined styles, single master, no slides.

**Represents.** A .pptx where the user *intended* a template but didn't follow naming conventions or define styles. Common in practice.

**Tests.** Graceful degradation. Does the validator surface the weakness? Does the remediator improve it?

**Pipeline.** Classifier → Extractor → Validator → Remediator.
