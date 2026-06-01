# Case 03 — Expected behavior (step-by-step validation guide)

The differentiator case. Score carefully.

## Stage 1 — Classifier

**File:** `01-classifier.json`.

**Step 1.1.** `classification`.

- `"deck-with-implicit-pattern"` → **Y**. The detection worked.
- `"mixed"` → **P**. Heuristic too lenient; would still route the user but with less certainty.
- `"template"` → **N**. The classifier missed — false positive. Differentiator broken.

**Step 1.2.** `confidence`.

- ≥ 0.30 → **Y** (low conf is OK on a sparse fixture).
- < 0.30 → **P**.

**Step 1.3.** `signals.default_layout_ratio`.

- ≥ 0.90 → **Y** (8/8 slides on Blank layout).
- 0.7-0.89 → **P**.
- < 0.7 → **N** (signal wrong).

**Step 1.4.** `signals.direct_overrides_per_slide`.

- ≥ 4 → **Y** (slides have many hand-positioned text boxes).
- 2-3 → **P**.
- < 2 → **N**.

## Stage 2 — Synthesizer

**Should have run** (`S-synthesized.pptx` should exist + `02-synthesizer-report.json`).

**File:** `02-synthesizer-report.json`.

**Step 2.1.** `n_clusters`.

- = 4 → **Y**. Matches the 4 patterns in the fixture.
- 3 or 5 → **P**. Close but not exact; clustering picked up 1 pattern as 2 or vice versa.
- < 3 or > 5 → **N**.

**Step 2.2.** `suggested_layout_map`.

Look at the keys. Expected: `title`, `three_pillars`, `metrics`, `quote`.

- All 4 expected intents present → **Y**.
- 3 of 4 → **P**.
- ≤ 2 → **N**.

**Step 2.3.** Look at `clusters[*].n_members`.

- Each cluster has 2 members → **Y**.
- One cluster has 1 + another has 3 → **P** (clustering split a pattern).
- Members very unevenly distributed → **N**.

**Step 2.4.** Open `S-synthesized.pptx` in PowerPoint.

- The 10 default layouts should have at least 4 renamed to `Title Slide`, `Three Column`, `Stat Block`, `Pull Quote` → **Y**.
- 2-3 of the 4 renamed → **P**.
- None renamed → **N**.

## Stage 3 — Extractor (on synthesized output)

**File:** `03-extractor.json`.

**Step 3.1.** `layout_map`.

- ≥ 7 of 10 intents → **Y** (4 synthesized + some default-named survivors).
- 5-6 → **P**.
- ≤ 4 → **N**.

**Step 3.2.** `quality_score`.

- ≥ 60 → **Y**.
- 40-59 → **P** (honest about barebones styling).
- < 40 → **N**.

## Stage 4 — Validator

**File:** `04-validator.json`.

Expected verdict: `"fail"` (the synthesized template is genuinely barebones — no color tokens, no type hierarchy, single master). Score:

- `verdict: "fail"` AND finding pattern shows expected reds on `color_tokens`, `type_tokens`, possibly `style_hierarchy` → **Y** (validator is being honest).
- `verdict: "pass"` → **N** (validator is being self-affirming).

## Stage 5 — Remediator

**File:** `R-remediated.pptx.audit.md`.

**Step 5.1.** Verdict comparison at the top.

- Before: `fail`. After: `fail` or `warn`. The applied fixes alone won't flip a barebones template to `pass` (color tokens still need user action) — that's expected and honest.
- After: `pass` → **P** (suspicious; likely scoring is too lenient).
- After: stayed `fail` with applied fixes → **Y**.

**Step 5.2.** Number of fixes applied.

- ≥ 2 (color palette + typeface recommendations) → **Y**.
- 1 → **P**.
- 0 → **N**.

**Step 5.3.** Audit entries — check rationale text reads sensibly.

- Rationales explain why each fix targets the validator finding → **Y**.
- Rationales generic/missing → **P**.

## Stage 6 — Renderer

**File:** `06-render.pptx` — open in PowerPoint.

**Step 6.1.** Slide count.

- 10 → **Y**.
- 9-10 → **P**.
- < 9 → **N**.

**Step 6.2.** Open `06-render.pptx.loss.md`.

- LOSSY count expected to be moderate (the synthesized template doesn't have all 10 intents → some substitutions in the manifest) → **Y** if 1-5.
- Very high LOSSY count → **P** (heavy substitution; might still be acceptable depending on which intents missed).
- LOSSY count 0 → **N** (suspicious; the synthesized template doesn't have full coverage so substitutions should happen).

## Overall verdict for case 03

- Stages 1, 2, 3 all **Y** AND stages 4, 5, 6 mostly **Y/P** → **PASS**. The detection-synthesis-remediation loop works.
- Stage 1 or 2 fails → **FAIL** (differentiator broken).
- Stages 3-6 fail but 1-2 pass → **PARTIAL** (detection works; downstream needs fixing).
