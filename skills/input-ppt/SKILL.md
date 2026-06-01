---
name: input-ppt
description: Accept legacy .ppt format by converting to .pptx via LibreOffice headless. Use when the user supplies a .ppt (old PowerPoint format) and downstream skills need .pptx. After conversion, the pptx pipeline runs as normal.
---

# input-ppt

Bridge skill for the legacy `.ppt` format. Converts to `.pptx` via LibreOffice headless; downstream skills then proceed against the converted file.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/input_adapter_ppt.py /path/to/deck.ppt \
  --out-dir /tmp/converted/
```

Output: `<deck>.pptx` in the output directory.

## Dependencies

LibreOffice (external binary). Install:

- macOS: `brew install --cask libreoffice`
- Linux: `apt-get install libreoffice`

The skill detects the binary at common paths (`libreoffice`, `soffice`, `/Applications/LibreOffice.app/...`) and errors clearly if not found.

## Composition

- **Downstream:** continue with `template-classifier --format pptx <converted.pptx>`.
- **Siblings:** `input-pdf` (PDF), `input-png` (images).
