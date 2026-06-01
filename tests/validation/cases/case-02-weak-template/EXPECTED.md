# Case 02 — Expected behavior (step-by-step)

A weak-template input. Validator should flag; remediator should improve.

## Stage 1 — Classifier

**File:** `01-classifier.json`.

- `classification: "template"` or `"mixed"` → **Y/P** (the file has layouts, no deck-with-implicit-pattern signal).
- `signals.layout_name_semantic_richness` ≤ 0.2 → **Y** (correctly observed weakness).
- If classification = `"deck-with-implicit-pattern"` → **N** (no slides, can't be a deck).

## Stage 2 — Synthesizer

Should NOT run (no deck-shape signal). If `S-synthesized.pptx` exists, **N**.

## Stage 3 — Extractor

**File:** `03-extractor.json`.

- `layout_map` mostly empty or very sparse (≤ 2 of 10 intents) — heuristic patterns don't match `Layout A`/etc → **Y**.
- `quality_score` ≤ 30 → **Y** (correctly observes the weakness).
- `quality_score` ≥ 70 → **N** (extractor is being too generous).

## Stage 4 — Validator

**File:** `04-validator.json`.

- `verdict: "fail"` → **Y**.
- Specifically: `layout_catalog_completeness` should be RED (no matched intents).
- `color_tokens` RED. `type_tokens` YELLOW. `style_hierarchy` likely RED.
- `master_usage` GREEN (single master).

## Stage 5 — Remediator

**File:** `R-remediated.pptx.audit.md`.

- ≥ 4 layout-rename fixes applied (Layout A→Title Slide, Layout B→Section Header, etc.) → **Y**.
- Color palette + typeface recommendations in audit → **Y**.
- Verdict improvement: before `fail` → after `fail` or `warn`. The remediator can't auto-fix everything (color tokens need user action) → **Y** if any improvement.

Open `R-remediated.pptx` in PowerPoint.

- The layouts should have been renamed → **Y**.

## Stage 6 — Renderer

May skip (no slides in input → may render against the renamed layouts with default profile). If `06-render.pptx` exists, open it.

- Slide count = 10 (from the IR) → **Y**.
- Layout substitutions in the loss manifest should now mostly be LOSSLESS (since the renaming created matches) → **Y**.

## Overall

- Validator catches weakness AND remediator improves the structure → **PASS**.
- Validator passes a weak template → **FAIL** (validator broken).
- Remediator doesn't apply layout renames → **PARTIAL** (validator works but remediator broken).
