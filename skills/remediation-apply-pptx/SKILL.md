---
name: remediation-apply-pptx
description: Apply automated remediation to a .pptx template that failed the validator. Use this skill whenever the template-validator returns warn or fail for a pptx target. Closes the detect → diagnose → fix loop so users don't have to manually edit their template in PowerPoint. Emits a remediated .pptx plus a fix-audit log naming every change made.
---

# remediation-apply-pptx

Automated remediation for a `.pptx` that the validator was unhappy with. v0.1 applies low-risk deterministic fixes via python-pptx; high-risk fixes (theme XML, master consolidation) are surfaced as recommendations the user applies in PowerPoint's Slide Master view.

## When this skill triggers

- `template-validator --format pptx` returns `warn` or `fail`.
- The user says "fix my template," "auto-fix this," "remediate this validator report."
- A render pre-flight fails because the template profile is below threshold.

## How to invoke

```bash
cd "<plugin-root>"
python adapters/remediation_apply_pptx.py /path/to/template.pptx \
  --out /path/to/remediated.pptx
```

If the validator hasn't been run yet, the adapter runs it transparently. To pass an existing validator report:

```bash
python adapters/remediation_apply_pptx.py /path/to/template.pptx \
  --validator-report /path/to/validator.json \
  --out /path/to/remediated.pptx
```

Outputs:

- `<out>.pptx` — the remediated template.
- `<out>.pptx.audit.md` — human-readable fix log.
- `<out>.pptx.audit.json` — machine-readable sidecar.

The audit log records every change applied, every change deferred (with the reason), and the validator verdict before vs. after. If the remediator did its job, the after-verdict is better than the before-verdict.

## v0.1 fix coverage

| Validator finding | Severity threshold | Action |
|---|---|---|
| `layout_catalog_completeness` | yellow or red | **Apply.** Rename existing layouts to match IR-intent semantic names. Improves layout coverage and reduces orphan elements simultaneously. |
| `color_tokens` | yellow or red | **Recommend.** Default brand-shaped palette surfaced in the audit. v0.1 doesn't auto-edit theme XML (corruption risk); the user pastes the palette into Slide Master → Colors → Customize Colors. |
| `type_tokens` | yellow or red | **Recommend.** Default typeface surfaced; the user applies via Slide Master → Fonts → Customize Fonts. |
| `style_hierarchy` | red | **Defer.** Adding distinct font-size tiers via XML edits is v0.2 scope. Audit notes the recommendation. |
| `master_usage` | yellow or red | **Defer.** Multi-master consolidation can break inheritance subtly. Audit logs the finding and recommends manual review in Slide Master view. |
| `orphan_elements` | yellow or red | **Indirect.** Resolved as a side-effect of the layout-rename fix (renamed layouts no longer count as orphans). |

## Why "apply" vs "recommend" vs "defer"

The split reflects automated-edit risk:

- **Apply** — the operation is deterministic and reversible by saving the file under a different name. Layout renaming is the v0.1 sweet spot: low-risk, high-impact, the synthesizer already does the same operation.
- **Recommend** — the operation is sound but requires editing theme/master XML where small mistakes corrupt the file. v0.1 generates the *content* (palette, typeface) so the user only has to apply it through the Office UI.
- **Defer** — the operation is judgment-heavy (which master to consolidate to? which size tier means heading-1 vs heading-2?). v0.1 punts; v0.2 will gain more confidence by training on real-world examples.

This split is explicit in the audit log so users know exactly what was automated and what wasn't.

## Composition with other skills

- **Upstream:** `template-validator` produces the JSON report this skill consumes.
- **Sibling:** `remediation-apply-figma` is the Figma counterpart (MCP-driven).
- **Downstream:** `template-extractor-pptx` runs on the remediated output to produce an improved profile entry. `template-validator` re-runs to confirm the verdict actually moved.

## Loop pattern (recommended by template-setup)

```
template-setup
   ├── template-classifier
   ├── template-extractor-pptx
   ├── template-validator       ← if verdict = fail or warn:
   ├── remediation-apply-pptx   ←   auto-apply fixes
   ├── template-validator       ← re-validate to confirm
   ├── template-extractor-pptx  ← re-extract for the lock profile
   └── lock profile.yaml
```

If the re-validation still returns `fail` after a remediation pass, `template-setup` surfaces the deferred findings to the user with a "next step is manual" message.

## Audit log format

```
# Fix audit — pptx auto-remediation

- Template (before): <path>
- Template (after): <path>
- Remediated: <ISO timestamp>
- Validator verdict before: <pass | warn | fail>
- Validator verdict after:  <pass | warn | fail>

## Summary
- Total fixes applied: N
- Findings deferred (manual review): N

### By fix type
- layout_rename: 3
- color_palette_recommended: 1

## Fixes applied
### 1. layout_rename — master.layout 'Custom Layout 1'
- Targets severity: layout_catalog_completeness
- Before: 'Custom Layout 1'
- After:  'Three Column'
- Why:    Renamed to match IR intent 'three_pillars'. ...
...

## Deferred — manual review recommended
- master_usage: Multi-master consolidation can break inheritance ...
```

The audit log doubles as the user-facing remediation report — no separate visual guide needed. The fixes ARE the report.

## v0.2 expansions (deferred)

- Auto-apply theme color tokens via OOXML theme XML editing (with safety nets).
- Auto-apply typeface registration.
- Auto-consolidate multi-master decks (with user confirmation per merge).
- Auto-add font-size tiers to the master.
- Optional **Claude in PowerPoint** integration mode: invoke the add-in's Skills surface to apply fixes interactively in the user's PowerPoint window. Stronger UX but requires the user's Claude subscription.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Reference

- Adapter: `adapters/remediation_apply_pptx.py`.
- Upstream skill: `template-validator/SKILL.md` (six criteria + severities).
- Loop pattern: `template-setup/SKILL.md` § "Branch B / Step 4".
