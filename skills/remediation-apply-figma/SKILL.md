---
name: remediation-apply-figma
description: Apply automated remediation to a Figma file that failed the validator. Use this skill whenever template-validator returns warn or fail for a Figma target. MCP-driven: a planning adapter computes the fix plan offline; Stage 2 executes the fixes via the Figma MCP. Closes the detect → diagnose → fix loop in Figma so users don't have to manually adjust styles or rename frames.
---

# remediation-apply-figma

The Figma counterpart to `remediation-apply-pptx`. Two stages: (1) compute the fix plan via the Python adapter; (2) execute the plan via the Figma MCP in the user's file.

## When this skill triggers

- `template-validator --format figma` returns `warn` or `fail`.
- The user says "fix my Figma template," "auto-remediate my Figma file."
- A figma-render pre-flight fails because the profile is below threshold.

## Pre-flight

1. **Figma MCP connected.** `cowork plugin grant slide-publisher --mcp figma` if not.
2. **Figma Desktop app open** with the target file active (Plugin API Rule 7).
3. **User confirmation.** This skill **writes to the user's file** (creates styles, renames frames). Ask before proceeding: "I'll apply N fixes to your Figma file (M styles created, K frames renamed). Proceed?" Wait for explicit yes.

## Stage 1 — Plan the fixes

```bash
cd "<plugin-root>"
python adapters/remediation_apply_figma.py /tmp/figma-walk-<file_key>.json \
  --validator-report /tmp/figma-validator-<file_key>.json \
  --out /tmp/figma-remediation-plan-<file_key>.json
```

Inputs:

- `walk.json` — output of the Figma MCP walk recipe (same one `template-synthesizer-figma` uses; see that skill's "Stage 1 — Walk the source slides").
- `validator.json` — output of `template-validator --format figma --profile-entry ...`.

Output: a JSON plan listing every fix to apply, grouped by type.

## Stage 2 — Execute the plan via Figma MCP

For each fix in `plan.fixes_to_apply`, dispatch on `fix_type`:

### `create_color_style`

```js
const style = figma.createPaintStyle();
style.name = fix.after.name;
style.paints = [{ type: 'SOLID', color: hexToRgb(fix.after.hex) }];
```

### `create_text_style`

```js
await figma.loadFontAsync({
  family: fix.after.family,
  style: weightToStyle(fix.after.weight),
});
const style = figma.createTextStyle();
style.name = fix.after.name;
style.fontName = {
  family: fix.after.family,
  style: weightToStyle(fix.after.weight),
};
style.fontSize = fix.after.size_pt;
```

### `rename_slide_template`

```js
const node = figma.getNodeById(fix.target.replace('node:', ''));
if (node) {
  // Update both the node name and its inner Heading > Title text
  // (Rule 2: title text is the reliable identifier).
  node.name = fix.after;
  const heading = node.children?.[0];
  const title = heading?.children?.[0];
  if (title && title.type === 'TEXT') {
    // Pre-load font (Rule 4)
    await figma.loadFontAsync(title.fontName);
    title.characters = fix.after;
  }
}
```

Apply all fixes in one Plugin API call (Rule 8). After each, log success or surface the failure.

## Stage 3 — Re-validate

After Stage 2 completes:

1. Re-run the walk recipe to capture the post-remediation state.
2. Re-run the extractor on the new walk to produce a fresh profile entry.
3. Re-run the validator on the fresh profile entry.
4. Append the post-verdict to the audit log.

## v0.1 fix coverage

| Validator finding | Severity threshold | Stage 2 action |
|---|---|---|
| `color_tokens` | yellow or red | Apply. Create named color styles via `figma.createPaintStyle()` from the default palette. |
| `type_tokens` | yellow or red | Apply. Create named text styles via `figma.createTextStyle()` from the default tier definitions. |
| `layout_catalog_completeness` | yellow or red | Apply. Rename slide-template frames (node + Heading title text) to IR-intent semantic names. |
| `live_structural_checks` | yellow (informational) | Defer to v0.2 (these checks aren't currently scored; addition needs live structural inspection). |

## The 8 Plugin API rules apply

See [`docs/FIGMA-PLUGIN-API-RULES.md`](../../docs/FIGMA-PLUGIN-API-RULES.md). Most relevant for remediation: Rules 4 (pre-load fonts before setCharacters), 5 (restore styling after setCharacters), 6 (verify title text after rename), and 8 (one batched Plugin API call per pass).

## Composition with other skills

- **Upstream:** `template-validator --format figma` produces the JSON this skill consumes.
- **Sibling:** `remediation-apply-pptx` is the pptx counterpart.
- **Downstream:** `template-extractor-figma` runs on the remediated walk to produce a fresh profile.

## Audit log

Same format as the pptx remediator's audit log — markdown + JSON sidecar. The Python planner emits the JSON; the user-facing markdown is rendered from it after Stage 2 completes (so it reflects what actually got applied, not just what was planned).

## v0.2 expansions

- Auto-consolidate slide template frames onto a dedicated "Templates" page (currently up to the user).
- Auto-create missing template frames (currently only renames existing ones).
- Detect and fix orphan frames.
- Integrate live structural validation criteria (style_hierarchy equivalent).

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Reference

- Adapter: `adapters/remediation_apply_figma.py`.
- Upstream skill: `template-validator/SKILL.md`.
- Walk recipe: `template-synthesizer-figma/SKILL.md` § "Stage 1".
