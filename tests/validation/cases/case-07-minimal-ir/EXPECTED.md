# Case 07 — Expected behavior

Minimal-but-valid IR.

## Stage 4 — Schema validation

**File:** `04-validator.json`.

- `schema_valid: true` → **Y**.
- `schema_valid: false` → **N** (something regressed in the schema).

## Stage 6 — Renderer

**File:** `06-render.pptx`.

- 3 slides → **Y**.
- All 3 titles visible → **Y**.
- Loss manifest: 4-6 DROPPED (deck-level fields) + 0-3 LOSSLESS (titles + minimal content) → **Y**.

## Overall

Slim IR renders cleanly → **PASS**. Renderer crashes or produces wrong count → **FAIL**.
