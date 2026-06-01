---
name: template-validator
description: Run the structural quality check over a slide-publisher template (pptx or Figma) and emit a green/yellow/red findings report with per-finding remediation. Use this skill whenever the user wants to "validate my template," "check if my deck is ready for slide-publisher," "audit my template," or "see what's wrong with my template." Also invoke proactively from template-setup right after extraction, before locking the profile.
---

# template-validator

Run the six-criteria structural quality check over a template and emit a findings report. The validator is the auditor that runs *after* the extractor — it tells the user what to fix before locking in the template profile.

## When this skill triggers

- The user says "validate my template," "audit my template," "check this deck."
- The user has just supplied a template path to `template-setup` and the orchestrator is at Step 4 (validation).
- The user wants to compare two template candidates and pick the better one.

## How to invoke

For a `.pptx` template:

```bash
cd "<plugin-root>"
python adapters/template_validator.py /path/to/template.pptx --format pptx
```

For a Figma template (requires an extractor-produced profile entry as input — v0.1 limitation):

```bash
cd "<plugin-root>"
python adapters/template_validator.py <file_key> --format figma --profile-entry candidate.json
```

Flags:

| Flag | Purpose |
|---|---|
| `--format pptx \| figma` | Required. Picks the validator path. |
| `--profile-entry <path>` | For Figma. Path to a JSON file containing the extractor's profile entry. |
| `--strict` | Exit non-zero on any yellow finding (default: only red fails). Use in pre-render gating. |
| `--out <path>` | Write JSON report to `<path>` instead of stdout. |

## Six criteria

Each criterion produces one finding, scored green / yellow / red. The overall verdict is the worst severity across findings:

- **pass** — all green.
- **warn** — at least one yellow, no red.
- **fail** — at least one red. In `--strict` mode, yellow also fails.

### 1. layout_catalog_completeness

**What:** How many of the 10 IR layout intents have a matching layout in the template?

- GREEN: 10/10.
- YELLOW: 7-9/10.
- RED: 0-6/10.

**Why:** Renderers fall back to "nearest available" on missing intents, and every substitution shows up in the loss manifest. Low coverage means visually inconsistent decks.

**Remediation:** Add layouts for the missing intents, or override the layout_map in `profile.yaml` to repurpose existing layouts.

### 2. style_hierarchy

**What:** How many distinct font-size tiers does the template define in its master(s)?

- GREEN: ≥4 tiers (e.g., heading-1, heading-2, body, caption).
- YELLOW: 2-3 tiers.
- RED: 0-1 tiers.

**Why:** Without a defined hierarchy, renderers can't infer visual emphasis from the IR's beat structure (a `claim` beat needs a heavier title than a `context` beat).

**Remediation:** Define explicit font-size tokens for heading, body, and caption tiers in the slide master.

### 3. master_usage *(pptx only)*

**What:** How many slide masters does the .pptx use?

- GREEN: 1.
- YELLOW: 2.
- RED: 3+.

**Why:** Multi-master decks fragment style inheritance. Slides on different masters can drift visually even when their content is identical.

**Remediation:** Consolidate to a single master. Move outlier layouts onto the primary master.

### 4. color_tokens

**What:** How many distinct color tokens did the extractor find in the master XML (pptx) or Styles → Colors panel (figma)?

- GREEN: ≥4.
- YELLOW: 2-3.
- RED: 0-1.

**Why:** Scattered hex values across slides make consistent rendering impossible. Tokens enable theming, dark mode, and brand updates.

**Remediation:** Define brand colors as explicit tokens (Theme colors in pptx, Color Styles in Figma).

### 5. type_tokens

**What:** How many distinct typefaces are explicitly named in the master?

- GREEN: 1-2 (display + body is the textbook split).
- YELLOW: 0 (theme-only) or >3 (too noisy).
- RED: (no fail mode for type tokens — typography is hard to evaluate from XML alone).

**Why:** Theme-only typography is workable but leaves the template at the mercy of Office's defaults. >3 typefaces is visual chaos.

**Remediation:** Pick 1-2 typefaces and define them as tokens in your theme.

### 6. orphan_elements *(pptx only)*

**What:** How many layouts in the template don't map to any IR intent?

- GREEN: <20% orphans.
- YELLOW: 20-49% orphans.
- RED: ≥50% orphans.

**Why:** Orphan layouts indicate either (a) legacy patterns nobody uses, or (b) specialized layouts the IR doesn't cover yet. Both are signals to clean up — orphans clutter the template and confuse renderers.

**Remediation:** Remove unused layouts, or propose adding their intents to the IR catalog (v0.2 scoping pass).

## Output format

```json
{
  "format": "pptx" | "figma",
  "verdict": "pass" | "warn" | "fail",
  "summary": {"green": 4, "yellow": 1, "red": 1},
  "findings": [
    {
      "criterion": "layout_catalog_completeness",
      "severity": "green",
      "value": "10/10",
      "message": "10 of 10 IR layout intents have a matching pptx layout.",
      "remediation": null
    },
    {
      "criterion": "master_usage",
      "severity": "red",
      "value": 3,
      "message": "3 slide masters in this template.",
      "remediation": "Consolidate to a single master..."
    }
  ]
}
```

Exit codes:

- 0 — `verdict: pass` (or `warn` in default mode).
- 1 — `verdict: fail`, or any non-green in `--strict` mode.
- 2 — dependency missing (python-pptx).

## Render-time gating

Renderers should run the validator in `--strict` mode before consuming a template. If the validator fails, the render aborts with the findings report attached. This is the contract: **a template that fails validation does not render**.

In default (lenient) mode the validator reports findings but doesn't block — useful during template authoring iterations.

## v0.1 limitations for Figma

The Figma validator runs only the three criteria available from the extractor's profile entry: `layout_catalog_completeness`, `color_tokens`, `type_tokens`. Live structural checks (`style_hierarchy`, `master_usage`-equivalent, `orphan_elements`) require live Figma MCP access and are deferred to v0.2.

For v0.1 Figma templates, supplement the validator's report with a manual inspection of the source file. The skill should surface this caveat in its quality report.

## Composition with other skills

- Called by `template-setup` Step 4, after extraction.
- Consumes output from `template-extractor-pptx` and `template-extractor-figma`.
- Output feeds the user-facing quality report in `template-setup` Step 5.
- Called by renderers (`render-pptx`, `render-figma`) in `--strict` mode as a pre-flight check.

## Anonymity (plugin policy)

Heuristics are generic; no organization-specific patterns, no user defaults baked in. The validator runs entirely against the user's input file and emits a structured report — no outbound calls, no telemetry.

## What this skill is NOT

- Not a template editor. The validator reports findings; the user fixes their source file.
- Not the extractor. The extractor *produces* the profile entry; the validator *audits* it (plus does additional live-template inspection for pptx).
- Not a style guide. The validator checks structural quality, not aesthetic quality. A well-structured template can still look bad; that's a separate concern.
