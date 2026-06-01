---
name: input-png
description: Accept one or more PNG screenshots as a deck source. Use when the user supplies images of slides as a visual reference — "use these screenshots as my reference," "match these slides," or when the input format isn't recoverable as native pptx/figma.
---

# input-png

Treats a set of PNG images as a deck. Optionally runs OCR (Tesseract) for text extraction; otherwise emits the image paths so visual-diff can still work.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/input_adapter_png.py slide-01.png slide-02.png slide-03.png \
  --out /tmp/png-as-slides.json \
  --ocr
```

## Dependencies

- `Pillow` (almost always already installed).
- `pytesseract` + Tesseract binary — only needed for OCR.
  - `pip install pytesseract`; `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Linux).

Without OCR the adapter still emits image paths and dimensions — visual-diff works; classifier/synthesizer see empty shape lists per slide.

## Composition

Same shape as `input-pdf`. Downstream: visual-diff (most common), classifier (limited without text).
