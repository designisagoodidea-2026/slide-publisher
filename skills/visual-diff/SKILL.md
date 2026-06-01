---
name: visual-diff
description: Compare an input deck (PNGs from any source format) against a rendered .pptx output, producing per-slide perceptual hash + SSIM similarity scores and an HTML side-by-side report. Use this skill to measure how visually close the rendered output is to the reference input — essential for iterate-to-parity loops and for validation.
---

# visual-diff

Quantifies and visualizes the gap between an input reference deck and a rendered output deck. Two metrics per slide: perceptual hash distance and SSIM similarity. HTML report with side-by-side images.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/visual_diff.py \
  --input-pngs slide-01.png slide-02.png ... \
  --output-pptx /path/to/rendered.pptx \
  --out-dir /tmp/diff/
```

Produces:

- `/tmp/diff/rendered/` — per-page PNGs from the rendered .pptx.
- `/tmp/diff/diff.html` — side-by-side HTML report with per-pair metrics + aggregate parity score.
- stdout: JSON summary with per-pair scores + aggregate.

## Dependencies

- `Pillow` for image I/O.
- `pdf2image` + LibreOffice — for converting .pptx → PDF → per-slide PNGs.
- `imagehash` (optional) — perceptual hash similarity. Fast, robust to small offsets.
- `scikit-image` + `numpy` (optional) — SSIM. More rigorous similarity.

If both `imagehash` and `scikit-image` are missing, the adapter still emits the HTML report but without numeric parity scores.

## Output

- **Per-pair:** `{phash_distance, phash_similarity, ssim, a (input PNG), b (rendered PNG)}`.
- **Aggregate parity:** mean of the SSIM column (or phash_similarity if SSIM unavailable). The aggregate is the convergence metric for `iterate-to-parity`.

## Composition

- **Upstream:** `input-pdf`/`input-png`/`input-ppt` produces the reference PNGs; one of the renderers produces the output .pptx.
- **Downstream:** `iterate-to-parity` consumes the per-pair scores as a feedback signal.
- **Validation:** every render in the validation harness gets a visual-diff against its source.

## Reference

- Adapter: `adapters/visual_diff.py`.
- HTML report shape: side-by-side table, one row per slide pair.
