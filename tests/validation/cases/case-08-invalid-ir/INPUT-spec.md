# Case 08 — Invalid IR

**Input.** `input.yaml` — missing required deck.throughline / deck.arc / deck.evidence_anchor; slide has invalid beat name `"intro"` and empty title.

**Tests.** Does the validator reject before render?

**Pipeline.** IR schema validation only. Renderer should NOT run.
