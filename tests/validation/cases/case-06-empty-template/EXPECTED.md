# Case 06 — Expected behavior

The empty-template corner case.

## Stage 1 — Classifier

- `classification: "mixed"` with `confidence: 0.0` AND diagnosis says "no slides, treat as template" → **Y**.
- Any other verdict without that diagnosis → **P** or **N**.

## Stage 2 — Synthesizer

Should NOT run. **N** if it did.

## Stage 3 — Extractor

- Still produces a `layout_map` from the default-named layouts (Title Slide, Title and Content, etc.) → **Y** if ≥ 4 intents matched.

## Stage 4 — Validator

- `verdict: "fail"` (no slides, weak structure) → **Y**.

## Stage 5 — Remediator

Renames default layouts to IR-intent names → **Y** if ≥ 4 fixes applied.

## Stage 6 — Renderer

Should be SKIPPED (no slides; renderer would have nothing to render slides over). **Y** if not run; **N** if it ran and errored badly.

## Overall

System handles the corner case without crashing; surfaces clear info → **PASS**.
