# Case 05 — Expected behavior

The mixed case. Classifier verdict matters most.

## Stage 1 — Classifier

- `classification: "mixed"` → **Y**.
- `classification: "template"` → **P** (some template structure is there; leaning that way is OK if confidence reflects uncertainty).
- `classification: "deck-with-implicit-pattern"` → **P** (some slides are deck-shaped; same idea).
- `signals.default_layout_ratio` ~ 0.5 → **Y** (correctly observes 2 of 4 on Blank).
- `signals.direct_overrides_per_slide` moderate (1-3) → **Y**.

## Stages 2-4

- Synthesizer may or may not run depending on classifier verdict. Either path is acceptable.
- Extractor finds the 5 named layouts → **Y** if 4-5 intents in layout_map.
- Validator: verdict `warn` or `fail`. RED on `layout_catalog_completeness` (only half intents present).

## Stages 5-6

- Remediator should rename remaining generic layouts (none here) and recommend palette/fonts.
- Renderer: slide count 10 (IR). Loss manifest reflects substitutions for missing intents.

## Overall

The classifier's primary job here is to FLAG ambiguity, not to commit to a verdict. If it returns `mixed` with sensible signals, the user gets the information needed to decide. **PASS** = the classifier signals uncertainty.
