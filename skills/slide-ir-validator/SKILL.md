---
name: slide-ir-validator
description: Validate a Deck IR YAML against the schema and run lint rules over it. Use this skill whenever the user has an IR file they want checked — even if they say "validate my deck," "check this IR," "lint my outline," "does my deck pass," or "what's wrong with my slides." Also use proactively right after story-compiler produces an IR, before handing back to the user, and right before render-pptx or render-figma consumes one.
---

# slide-ir-validator

Run schema validation + content lint over a Deck IR YAML. Return pass/fail + a list of findings categorized by severity. The validator is the gate between authoring and rendering; renderers should refuse to consume an IR that fails validation in `--strict` mode.

## When this skill triggers

- The user says "validate," "check," "lint," "does my IR pass."
- The story-compiler skill has just emitted an IR (run validation before returning to the user).
- A render-pptx or render-figma skill is about to consume an IR (run validation before render).
- The user pastes an IR and asks "what's wrong with this" or "is this ready to render."

## Two checks: schema + lint

### Schema validation (hard fail)

The IR YAML must validate against `ir/schema.json` (JSON Schema 2020-12). Use any conforming validator (Python `jsonschema>=4.18`, JavaScript `ajv`, Go `gojsonschema`). Schema violations are hard fails — the renderers depend on the structure being correct.

Common schema failures and what they mean:

- `'X' is a required property` on `deck` — the outline is missing one of the required deck-level fields (`title`, `audience`, `throughline`, `arc`, `evidence_anchor`). Refer the user back to story-compiler to fill it in.
- `'X' is not one of ['hook', 'context', …]` on a slide's `beat` — beat names must come from the 9-value catalog. Often a typo (e.g., `intro` instead of `hook`).
- `'X' is not one of ['title', 'section_break', …]` on `layout_intent` — same story for the 10-value layout catalog.
- `'' should be non-empty` on a slide `title` — every slide has a non-empty title. Even quote slides — the title can be the slide's purpose label that the renderer chooses to render small or hide.
- `Additional properties are not allowed` — the IR has a field outside the schema. Strip it; if it's load-bearing, propose adding it to the schema as a v0.2 surface.

### Lint (configurable severity)

The lint rules check things schema can't — content-level concerns. Each finding has a severity: `error`, `warn`, or `info`. In default mode the validator reports all findings and exits 0 unless there's a schema failure or an error-severity lint. In `--strict` mode it exits non-zero on any error-severity lint.

#### LINT-001 — Missing speaker notes on load-bearing beats

**Severity:** warn (default), error (`--strict`).

**Rule:** Slides with `beat` in `{claim, evidence, tension, resolution}` should have non-empty `speaker_notes`. These beats do real narrative work; a speaker without notes is a speaker reading the slide aloud.

**Remediation:** Add 2-3 sentences of speaker context. Don't repeat the title or body verbatim — add what *won't* fit on the slide.

#### LINT-002 — Layout-intent / beat mismatch

**Severity:** warn.

**Rule:** A beat should map to a layout intent in its allowed set (see story-compiler's `Beat → layout-intent mapping` table). Defaults plus the documented alternatives are allowed; anything outside that set triggers this lint.

| Beat | Allowed layout intents |
|---|---|
| `hook` | `title`, `callout`, `quote`, `section_break` |
| `context` | `claim_with_evidence`, `timeline`, `metrics`, `section_break`, `image_with_caption` |
| `problem` | `claim_with_evidence`, `comparison`, `metrics`, `callout` |
| `claim` | `claim_with_evidence`, `callout`, `three_pillars` |
| `evidence` | any (depends on evidence anchor) |
| `tension` | `comparison`, `claim_with_evidence`, `metrics`, `three_pillars` |
| `resolution` | `three_pillars`, `claim_with_evidence`, `callout`, `timeline` |
| `callback` | `callout`, `quote`, `claim_with_evidence` |
| `next` | `callout`, `timeline`, `claim_with_evidence` |

**Remediation:** Either change the layout intent to fit the beat, or change the beat name to fit the intended slide function. Don't suppress this warning by editing the rule — that's a sign the catalog needs a v0.2 expansion.

#### LINT-003 — Throughline drift

**Severity:** info.

**Rule:** At least one of `claim` or `callback` slides should reference the throughline — either as the title, in a body block, or in speaker notes. The check is fuzzy (substring match on 3+ meaningful words from the throughline); false positives happen and are fine.

**Remediation:** If the throughline doesn't appear anywhere, either the deck has drifted from its premise or the throughline was never internalized. Rewrite the throughline to match what the deck is actually saying, or rewrite the deck to land what the throughline promises.

#### LINT-004 — Missing transitions on long decks

**Severity:** info.

**Rule:** Decks with 10+ slides should have at least 50% of slides populating `transitions.from_prior` or `transitions.to_next`. Without transitions, the IR carries no narrative connective tissue, and the speaker has to invent it live.

**Remediation:** Add `transitions.from_prior` to mid-deck slides — one short sentence describing why this slide follows the last one.

#### LINT-005 — Evidence anchor mismatch

**Severity:** warn.

**Rule:** Slides with `beat: evidence` should match the deck's `evidence_anchor`:

- `numbers` → `metric` body blocks or `metrics` layout intent.
- `story` → `quote` body blocks or `image_with_caption` (a moment, a face).
- `demo` → `image_placeholder` or `diagram_placeholder`.
- `framework` → `three_pillars`, `diagram_placeholder`, or `timeline`.
- `hybrid` → any of the above; no lint.

**Remediation:** Either change the evidence anchor at the deck level (the deck might actually be a different shape than authored) or change the evidence slides to match.

#### LINT-006 — Beat ordering sanity

**Severity:** warn.

**Rule:** Beats should appear in a plausible narrative order. Hard checks:

- `hook` must appear before any `evidence` or `resolution`.
- `next` must be the last beat in the deck (or absent).
- `callback` should appear after at least one `claim`.

**Remediation:** Reorder slides or rename beats. If the deck is deliberately out-of-order (e.g., a reverse-chronological deck), set `deck.arc: reverse-chronological` — the lint loosens checks #1 and #3 in that arc.

#### LINT-007 — Body block kind / layout intent fit

**Severity:** info.

**Rule:** Some layout intents expect particular body-block kinds.

- `metrics` should contain ≥1 `metric` body block.
- `quote` should contain ≥1 `quote` body block.
- `three_pillars` should contain a `bullets` block with ≥3 items, or three separate prose/metric blocks.
- `comparison` should contain ≥2 body blocks of similar shape (e.g., two `bullets`, two `metric`).

**Remediation:** Reshape the body blocks to match, or pick a different layout intent.

## Output format

```yaml
validation:
  schema: pass | fail
  schema_errors:
    - path: $.slides[3].beat
      message: "'intro' is not one of ['hook', 'context', ...]"
  lint:
    pass: true | false
    findings:
      - rule: LINT-001
        severity: warn
        path: $.slides[5]
        slide_id: claim-slide
        message: "Missing speaker notes on a 'claim' beat."
        remediation: "Add 2-3 sentences of speaker context."
      - ...
  summary:
    schema_errors: <int>
    lint_errors: <int>
    lint_warnings: <int>
    lint_info: <int>
  verdict: pass | warn | fail
```

`verdict` is the headline:

- `pass` — schema pass + zero error-severity lints + zero warns (`--strict`) or zero errors (default).
- `warn` — schema pass + zero error-severity lints, but ≥1 warn.
- `fail` — schema fail OR ≥1 error-severity lint (`--strict` promotes warns to errors).

Exit code follows verdict — 0 for `pass` and `warn` in default mode, non-zero for `fail`. In `--strict`, only `pass` is exit 0.

## Strict mode

`--strict` promotes warns to errors. Use it before render — a renderer should refuse to consume an IR that doesn't pass `--strict`. Use default mode during authoring — warns are signal but not blocking.

## What this skill is NOT

- Not a story coach. The lint flags structural issues; it does not rewrite content. If LINT-003 (throughline drift) fires, the validator reports the drift but does not propose a new throughline.
- Not a renderer pre-flight. Renderers run their own checks (layout-map coverage, asset availability) on top of IR validity.
- Not a stylistic lint. Voice, tone, and word choice are out of scope for v0.1. v0.2 may add a `voice_constraints` integration point.

## Reference

Schema authoritative source: `ir/schema.json`. Don't duplicate schema rules in the lint — let the schema gate hard structure; let lint catch what the schema can't express.

Three example IRs at `ir/examples/` all validate clean against both schema and lint. Use them as known-good fixtures when developing the lint engine.
