---
name: template-extractor-pptx
description: Synthesize a slide-publisher template profile from a loose .pptx deck (or an existing .pptx template). Use this skill when the user supplies a .pptx file as part of the template-setup workflow — even when they say "use this deck as a starting point," "build a template from this," or "make this work with slide-publisher." Wraps the adapters/template_extractor_pptx.py script and produces a candidate template-profile entry for the user to review.
---

# template-extractor-pptx

Inspect a `.pptx` file, infer the IR layout-intent map and style tokens, and emit a candidate template-profile entry. The skill is a wrapper around `adapters/template_extractor_pptx.py` — the script does the heavy lifting; this skill explains when and how to invoke it, and how to interpret the output.

## When this skill triggers

Trigger any time a `.pptx` file is the input and the goal is to make it work with slide-publisher:

- The user is running `template-setup` and supplies a `.pptx` path.
- The user says "build me a template from this deck" + attaches a `.pptx`.
- The user has an existing `.pptx` template and wants to validate that slide-publisher can render against it.

Do NOT trigger when:

- The user has a Figma file — use `template-extractor-figma` instead.
- The user has Google Slides — defer; the gslides extractor lands in v0.2.
- The input is a `.pptx` deck that the user wants *rendered into*, not *learned from* — that's the `render-pptx` skill's job.

## How to invoke

Run the adapter as a Python script:

```bash
cd "<plugin-root>"
python adapters/template_extractor_pptx.py /path/to/template.pptx
```

Common flags:

| Flag | Purpose |
|---|---|
| `--out <path>` | Write JSON to `<path>` instead of stdout. |
| `--strip-debug` | Omit `_inspected_layouts` and `_findings` from output. Use when piping into a downstream skill or persisting to `profile.yaml`. |

Requires `python-pptx`. If missing, the script exits with code 2 and a clear install hint (`pip install python-pptx`). The plugin's install README should document this dependency.

## Output shape

The adapter emits JSON with this shape:

```json
{
  "layout_map": {
    "title": "Title Slide",
    "section_break": "Section Header",
    "claim_with_evidence": "Title and Content",
    ...
  },
  "style_tokens": {
    "colors": {
      "primary": "#1F2A44",
      "secondary": "#3F6AB1",
      ...
    },
    "typography": {
      "heading-1": {"family": "Inter", "size_pt": 40.0, "weight": 700},
      "body": {"family": "Inter", "size_pt": 18.0, "weight": 400},
      ...
    }
  },
  "quality_score": 88,
  "_inspected_layouts": ["Title Slide", "Section Header", ...],
  "_findings": [
    "All 10 IR layout intents have a matching pptx layout. Clean coverage.",
    "..."
  ]
}
```

- `layout_map` and `quality_score` populate the template-profile schema's `templates.pptx` branch.
- `style_tokens` populates the schema's top-level `style_tokens`.
- `_inspected_layouts` lists every layout found across all masters (debug).
- `_findings` is a human-readable summary of completeness gaps. Surface these to the user verbatim during template-setup's quality report.

## How the inference works (so you can explain it to the user)

1. **Layout map.** The adapter walks every slide master and slide layout in the .pptx, collecting their names. It then matches each of the 10 IR layout intents against those names using a small pattern dictionary (e.g., `"three_pillars"` matches names containing "three", "3 column", "pillars"). First match wins; each layout name is used at most once.
2. **Color tokens.** The adapter walks the master XML and counts every `<a:srgbClr>` element. The top 8 most frequent colors are assigned generic role names (`primary`, `secondary`, `accent`, ...). The user can rename downstream.
3. **Typography.** Same approach for fonts and sizes — most-common typeface, top 5 distinct font sizes mapped to `heading-1` through `caption`.
4. **Quality score.** A weighted heuristic: 50% layout coverage, 20% layout breadth, 15% color completeness, 15% type completeness. 0-100 scale.

These are heuristics, not authoritative. The user reviews and edits before the profile is locked.

## When the heuristic doesn't fit

- **Layout name mismatch.** If the .pptx uses non-English or custom layout names (e.g., "Mise en page principale"), the pattern dictionary won't match. The user should add an explicit layout map override in their `profile.yaml`.
- **Layouts inherit from a non-default master.** Multi-master decks are valid but make catalog inference flaky. Suggest consolidating to a single master before locking the profile.
- **Theme colors only, no explicit srgbClr.** Some templates rely entirely on Office theme colors. `_findings` will note "No explicit color tokens extracted"; the renderer will inherit from the master at render time. This is fine — just informational.

## Process — inside template-setup

When invoked as a sub-skill from `template-setup`:

1. Receive the .pptx path from the wizard.
2. Run the adapter with `--strip-debug`.
3. Parse the JSON output.
4. Read `_findings` (re-run without `--strip-debug` to surface findings).
5. Pass results back to `template-setup` for the quality report + `template-validator` cross-check.
6. On user confirmation, the orchestrator merges the result into `profile.yaml`.

## What this skill is NOT

- Not a quality validator. The extractor produces a *candidate* profile and a *first-pass* quality score. The full structural quality check (orphan layouts, master fragmentation, style hierarchy depth) is `template-validator`'s job — that runs *after* extraction.
- Not a renderer. The adapter does not touch the user's deck content; it only inspects the master/layout structure.
- Not a Figma extractor. Figma has its own adapter and skill.

## Anonymity (plugin policy)

This skill ships in the public, anonymous plugin. The adapter contains no hard-coded organization mappings, no proprietary patterns, no user-specific defaults. The pattern dictionary is generic. The default token role names (`primary`, `body`, etc.) are universal.

The script's output reflects the user's input only — running it on `their_template.pptx` produces values derived from that file. No outbound network calls.
