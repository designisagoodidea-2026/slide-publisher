---
name: input-pdf
description: Accept a PDF (URL or local path) as a deck source. Extracts per-page text + positions and (optionally) renders pages to PNG for visual diffing. Use when the user supplies a PDF as a reference deck — "use this PDF as my reference," "import this slide PDF," "match this exported deck."
---

# input-pdf

Multi-format input adapter for PDF sources. Normalizes a PDF into the slide-shape JSON the classifier / synthesizer / visual-diff downstream skills consume.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/input_adapter_pdf.py <pdf-url-or-path> \
  --out /tmp/pdf-as-slides.json \
  --render-pngs
```

`--render-pngs` is needed when the downstream step is `visual-diff`. Otherwise omit (faster).

## Dependencies

- `pdfplumber` — text + position extraction. `pip install pdfplumber`.
- `pdf2image` + poppler — page-to-PNG rendering. `pip install pdf2image`; `brew install poppler` (macOS) or `apt-get install poppler-utils` (Linux).

If pdf2image isn't available, the adapter still emits the slide-shape JSON without `png_path` fields — visual-diff won't work but classification + synthesis can still run.

## Output shape

Same shape the Figma MCP walk produces — slides with shapes, allowing downstream skills to treat PDF as just another input format. See `adapters/input_adapter_pdf.py` docstring for the field reference.

## Composition

- **Downstream:** `template-classifier`, `template-synthesizer-pptx`/`-figma`, `visual-diff`.
- **Siblings:** `input-png` (image-only inputs), `input-ppt` (legacy .ppt).
