# Case 01 — Expected behavior (step-by-step validation guide)

Baseline well-formed template. Score Y/N/P per check.

## Stage 1 — Classifier

**File to open:** `01-classifier.json`

**Step 1.1.** Look at the top-level `classification` field.

- If it reads `"template"` → **Y** for this check.
- If it reads `"deck-with-implicit-pattern"` → **N**. The classifier failed to recognize a real template. This is diagnostic of a heuristic-weight bug — likely the synthetic-template's layouts aren't matching the semantic-richness pattern dictionary even though they have IR-intent names.
- If it reads `"mixed"` → **P**. The classifier is uncertain. Look at `confidence`: if ≥0.5, lean Y; if <0.5, lean N.

**Step 1.2.** Look at `confidence`.

- ≥ 0.65 → **Y**.
- 0.40-0.64 → **P**.
- < 0.40 → **N** (verdict is right but the confidence is too shaky to trust).

**Step 1.3.** Inspect `signals.layout_diversity_ratio`.

- Expected ≥ 0.9 (10 layouts used across 10 slides). If lower, the underlying fixture has changed unexpectedly.

**Step 1.4.** Inspect `signals.layout_name_semantic_richness`.

- Expected ≥ 0.7 (most layout names contain IR-intent words). If lower, the synthetic template's layout names regressed.

## Stage 2 — Synthesizer

**Should NOT have run** for this case. If `S-synthesized.pptx` exists, score this stage **N** — the classifier failed to route correctly.

## Stage 3 — Extractor

**File to open:** `03-extractor.json`

**Step 3.1.** Look at `layout_map`.

- All 10 IR intents present as keys → **Y**.
- 7-9 keys → **P**.
- ≤ 6 keys → **N** (something broke the pattern matching).

**Step 3.2.** Look at `quality_score`.

- ≥ 80 → **Y**.
- 50-79 → **P**.
- < 50 → **N**.

## Stage 4 — Validator

**File to open:** `04-validator.json`

**Step 4.1.** Look at `verdict`.

- `"pass"` → **Y**.
- `"warn"` → **P** — likely color_tokens or type_tokens because synthetic-template uses theme-only styles.
- `"fail"` → **N**.

**Step 4.2.** Inspect each criterion in `findings`.

- `layout_catalog_completeness`: expect green.
- `master_usage`: expect green (single master).
- `color_tokens`, `type_tokens`: yellow is expected (theme-only).
- `style_hierarchy`, `orphan_elements`: green expected.

## Stage 5 — Remediator

**Should NOT have run** (verdict was pass/warn but not requiring remediation in v0.1 default mode). If `R-remediated.pptx` exists, score **N**.

## Stage 6 — Renderer

**File to open:** `06-render.pptx` — open in PowerPoint.

**Step 6.1.** Slide count.

- 10 slides → **Y**.
- 9-10 slides → **P**.
- < 9 slides → **N**.

**Step 6.2.** Open each slide and check the title.

- Each slide title matches the corresponding IR slide's `title` field → **Y**.
- 1-2 titles wrong or missing → **P**.
- ≥3 titles wrong → **N**.

**Step 6.3.** Open `06-render.pptx.loss.md`.

- LOSSY count = 0 (well-formed template should have clean layout matches) → **Y**.
- LOSSY count 1-2 → **P**.
- LOSSY count ≥ 3 → **N**.

- DROPPED count = 5-6 (deck-level story-frame fields) → **Y**. Other counts mean something else broke.

## Overall verdict for case 01

- All stages **Y** → **PASS**.
- 1-2 stages **P**, no **N** → **PARTIAL**.
- Any stage **N** → **FAIL**.

If FAIL, the failure mode points at which subsystem to debug:

- Classifier failures → heuristic weights or pattern dictionary.
- Extractor failures → layout discovery or pattern matching.
- Renderer failures → layout resolution or placeholder population.
