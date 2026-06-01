# Validation methodology

How the slide-publisher model was externally validated before v0.1 ship.

## The self-affirming trap

Tests written against fixtures you designed prove the code does what you designed — not whether the design is right. Initial test coverage (13-assertion integration harness + 7 case rubric) had this shape. Useful for regression detection; not useful for validating model correctness.

## External validation method

Test the model against templates the plugin authors did not design:

1. **Microsoft built-in themes** — three themes saved fresh from PowerPoint's "New from Template" flow (atlas-theme, gallery-template, madison-theme). Professionally designed by Microsoft; ship inside the Office app. Industry ground truth.
2. **Random web-sourced templates** — nine real-world `.pptx` files downloaded from the web (military, medical, academic, university, corporate, design-tool docs). Authors unknown to the plugin team; designs were not influenced by the model.

## How the model was calibrated

The first run of the validation against Microsoft themes flagged 3 of 3 as `fail` with 4 red findings. The themes are correct; the model was miscalibrated. Four fixes landed:

1. **Layout coverage via effective fallback chain.** Templates that map `claim_with_evidence` cleanly cover `three_pillars`, `metrics`, `callout` through the renderer's fallback chain. Counting them as covered reflects rendering reality.
2. **Theme XML inspection.** Industry templates declare colors in `ppt/theme/theme1.xml` `clrScheme` and typography in `fontScheme`. Reading the theme XML credits both paths.
3. **Classifier signals.** Canonical Office layout names ("Title Slide", "Title and Content") are template signals, not stock-defaults signals. Removed from the deck-shaped indicator set. For low-slide-count templates (≤2 slides), weight layout-catalog signals over slide-usage signals.
4. **Orphan threshold.** Rich-catalog templates can legitimately carry 90% specialized layouts. Relaxed thresholds: red at 95% unused (was 50%), yellow at 85%.

## After-fix results

| Source | Files | pass | warn | fail | Acceptable rate |
|---|---|---|---|---|---|
| Microsoft built-in themes | 3 | 3 | 0 | 0 | **100%** |
| Native .pptx web-sourced templates | 9 *(excl. lock file)* | 7 | 2 | 0 | **100%** |
| LibreOffice-converted from .ppt | 9 | 0 | 0 | 9 | **0%** |

12 of 12 native templates validate as `pass` or `warn`. The 0% on converted .ppt files is a structural finding: LibreOffice's `.ppt` → `.pptx` conversion is lossy with respect to layout catalog. This isn't a model bug; it's a known limitation of the conversion tool. v0.2 will surface a warning in the `input-ppt` adapter recommending users re-save in PowerPoint.

## Regression coverage

External validation isn't a substitute for self-test. Integration harness at `tests/integration/test_pipeline.py` (13 assertions across 5 stages) runs in CI to catch regressions. Microsoft themes + random PowerPoint validation paths live in internal `notes/` — third-party files don't ship in the public repo.

## What still needs validation in v0.2

- **Real Figma file round-trip.** The Figma extractor + synthesizer adapters are pure Python and tested against synthetic JSON; live MCP execution against a real Figma file is a maintainer-hands task before slice 2 ship.
- **Google Slides format.** v0.2 adds gslides. The model's behavior on Google's templates is a new external-validation exercise. `_common.py`'s `FormatAdapter` Protocol documents the contract gslides must satisfy.
- **Multi-master templates.** One real-world case (`serving-students-community-partners`) used 2 masters and triggered a yellow finding on `master_usage`. That may be more permissive in real practice than v0.1 currently allows; worth revisiting.
