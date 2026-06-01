# Scoresheet

Fill in per case after running `tests/validation/run_validation.py` and reviewing each `EXPECTED.md`. Each cell: **Y** (pass), **N** (fail), **P** (partial), or **n/a** if the case doesn't exercise that stage.

| Case | Classifier | Synthesizer | Extractor | Validator | Remediator | Renderer | Visual diff | Overall | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 01-well-formed-template | | n/a | | | n/a | | | | |
| 02-weak-template | | n/a | | | | | | | |
| 03-canonical-deck | | | | | | | | | |
| 05-mixed | | | | | | | | | |
| 06-empty-template | | n/a | | | | n/a | n/a | | |
| 07-minimal-ir | n/a | n/a | n/a | | n/a | | | | |
| 08-invalid-ir | n/a | n/a | n/a | | n/a | n/a | n/a | | |

Internal (not in public repo; require your own real-world inputs):

| Case | Classifier | Synthesizer | Extractor | Validator | Remediator | Renderer | Visual diff | Overall | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 04-real-pptx (your deck) | | | | | | | | | |
| 09-real-figma-template | | n/a | | | n/a | | | | |
| 10-real-figma-deck | | | | | | | | | |

**Overall verdict:** _____ (PASS / PARTIAL / FAIL)

**Findings to address before slice 1 ship:**

1.
2.
3.

**Findings to defer to v0.2:**

1.
2.
3.
