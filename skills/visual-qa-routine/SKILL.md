---
name: visual-qa-routine
description: Continuous visual regression detection + automated improvement for slide-publisher renders. Run before any change to a renderer (pptx, figma, or future gslides), and as part of preflight. Captures baselines, diffs against them, surfaces anomalies, and feeds them into a remediation loop. Use whenever the user changes pptx_renderer.py, figma_yaml_emitter.py, _common.py rendering helpers, or any template-touching adapter.
---

# visual-qa-routine

Slide-publisher produces visual artifacts. Code-level tests catch IR validation, layout binding, and content presence — they don't catch overflow, font substitution, missing decorative elements, or layout selection mismatches. Those are visible only by rendering and looking.

This routine wraps render + screenshot + diff + diagnose + auto-improve into a single deterministic loop, wired into `uat/preflight.py` so that drift can't pass silently.

## When this skill triggers

- Before any change to a renderer (`adapters/pptx_renderer.py`, `adapters/figma_yaml_emitter.py`, future gslides renderer).
- Before any change to `_common.py` body-block rendering helpers, layout fallback chain, or token resolution.
- As part of `uat/preflight.py` — visual regression is a BLOCKER finding.
- After adding a new template fixture to `notes/microsoft-themes/` or equivalent.

## The 5 components

```
tests/visual-qa/
    run_renders.py         ← (1) Matrix harness
    baselines.yaml         ← (2) Per-render expected hash + SSIM threshold
    baselines/             ← (2) Reference PNGs
    runs/<timestamp>/      ← Per-run output: PNGs + summary
adapters/
    visual_diff.py         ← (3) pHash + SSIM + per-region delta
    visual_anomaly_diagnose.py  ← (4) Rules-based classifier
    iterate_to_parity.py   ← (5) Auto-remediation loop
```

### 1. Render harness — `tests/visual-qa/run_renders.py`

Matrix runner over (IR, template, renderer) tuples. For each:

1. Extract template profile (`template-extractor-pptx`).
2. Wrap as profile YAML (`templates.pptx` branch).
3. Render IR + profile → `.pptx` (`pptx_renderer`).
4. Convert `.pptx` → PDF (LibreOffice headless) → per-slide PNGs (`pdftoppm`).
5. Compare each PNG against the baseline (lightweight byte-hash check; full diff via component #3 when drift detected).

Output: `tests/visual-qa/runs/<timestamp>/<ir>/<template>/<renderer>/slide-N.png` plus `summary.md` + `summary.json`. Last `--keep-runs` (default 5) retained; older pruned.

Invocation:

```bash
cd "<plugin-root>"
python3 tests/visual-qa/run_renders.py                  # diff-only run
python3 tests/visual-qa/run_renders.py --capture-baseline  # establish/refresh baselines
```

**Figma renders** are not part of the automated matrix because they require live MCP access. v0.2.x will add a chat-mediated mode that emits a publish-payload + screenshot-payload the user runs in a Claude session.

### 2. Baseline manifest — `tests/visual-qa/baselines.yaml`

Per-render key entry:

```yaml
design-system-retro__atlas-theme__pptx:
  captured_at: 2026-06-02T02:42:14
  n_slides: 10
  ssim_threshold: 0.92
  slides:
    - slide: slide-01.png
      sha256_16: 293ac81c55d57d37
      size_bytes: 75188
```

Updated when `--capture-baseline` is passed. Reference PNGs live in `tests/visual-qa/baselines/<key>/`. Baselines represent "the render the team has reviewed and accepted." Changes to them are deliberate.

### 3. Diff engine — `adapters/visual_diff.py` (extended)

Existing v0.1 adapter does pHash + SSIM. v0.2 extends with per-region delta (split each slide into title-band, body-band, footer-band; report delta per region so the diagnose step can localize anomalies).

### 4. Root-cause classifier — `adapters/visual_anomaly_diagnose.py`

Rules-based at v0.1. Each rule maps an anomaly signature to a structured finding:

| Anomaly | Signal | Finding | Recommended fix |
|---|---|---|---|
| title_overflow | Title bbox extends > template placeholder + 5% | IR title len > template-supported title chars | Shorten IR title OR pick a less-constrained intent |
| missing_fill | Template placeholder had fill, render slot empty | Renderer cleared fills during placeholder reset | Restore fill-preservation in renderer |
| font_substitution | Computed text font ≠ profile typography token | Required font not installed on render host | Install font OR fall back to profile's `safe_alternate` |
| empty_body | IR body content non-empty, BODY placeholder empty | Layout binding failed silently | Surface as DROPPED in loss manifest |
| missing_decoration | Template had decorative shapes, render missing them | Renderer's `_strip_existing_slides` removed them | Adjust strip rule to preserve `non_placeholder=True` shapes |

Each finding includes the responsible IR field, layout binding, or renderer setting + a recommended fix.

### 5. Auto-remediation loop — `adapters/iterate_to_parity.py` (extended)

For findings with deterministic fixes (e.g., shorten IR title to fit, swap to fallback intent), apply and re-render. Iterate up to N (default 5) iterations until SSIM ≥ threshold or no more deterministic fixes available. Output: a remediation audit log naming every iteration's anomaly + fix + result.

## Preflight integration

`uat/preflight.py` gains:

```python
def check_visual_regression(caps, r):
    """Run tests/visual-qa/run_renders.py and BLOCK if any baseline drift."""
```

Blocks on regression > threshold. Warns on `new` (no baseline yet, needs capture). Passes when all renders match baselines within SSIM ≥ 0.92.

## v0.1 scope (this iteration)

✓ Component 1 (render harness) — built, smoke-tested against 5 of 9 (IR × template) tuples.
✓ Component 2 (baselines) — captured for 5 tuples.
⏳ Component 3 (extended diff) — v0.1 has pHash + SSIM only; per-region delta is v0.2.x.
⏳ Component 4 (anomaly diagnose) — design captured in this SKILL.md; implementation is v0.2.x.
⏳ Component 5 (auto-remediation) — v0.2.x extension to `iterate_to_parity.py`.
⏳ Preflight `check_visual_regression` — currently a warning-only stub.

## Reference

- Memory: `feedback_visual_qa_routine.md` — the principle (continuous, mechanical, preflight-enforced).
- Architecture doc: `docs/LOSS-MANIFEST.md` — anomaly findings feed the loss manifest.
- Adapter docs: `adapters/visual_diff.py`, `adapters/iterate_to_parity.py`.
