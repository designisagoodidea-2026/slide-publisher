# Case 08 — Expected behavior

Invalid IR — gate must catch it.

## Stage 4 — Schema validation

**File:** `04-validator.json`.

- `schema_valid: false` → **Y**.
- `errors` array contains entries for:
  - Missing `deck.throughline` / `deck.arc` / `deck.evidence_anchor` (required fields).
  - Invalid `slides[0].beat: "intro"` (not in enum).
  - Empty `slides[0].title` (minLength 1).
- ≥ 3 of those errors present → **Y**.
- < 3 → **P** (validator missing some checks).
- `schema_valid: true` → **N** (validator is broken).

## Stage 6 — Renderer

Should NOT run. If `06-render.pptx` exists → **N**.

## Overall

Validator catches the invalid IR and refuses to proceed → **PASS**. Validator passes garbage → **FAIL**.
