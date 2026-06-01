---
name: template-setup
description: Run the one-time slide-publisher install wizard that ingests the user's existing decks or templates and produces a persistent template profile. Use this skill the first time the plugin is used, when the user asks to "set up slide-publisher," "configure the plugin," "import my template," "re-run setup," "change my default render target," or any phrase that implies establishing or updating the per-install template profile. Also use proactively when a render-pptx or render-figma skill is invoked and no profile exists yet — setup is required before rendering.
---

# template-setup

The install wizard for slide-publisher. Runs once at first use (or any time the user wants to update). Produces `~/.cowork/plugins/slide-publisher/profile.yaml`, the persistent template profile that every renderer reads.

## When this skill triggers

- First-run flow after `cowork plugin install slide-publisher`.
- The user says "set up the plugin," "configure slide-publisher," "import my template," "switch my default to Figma," "re-run setup," or anything implying profile creation/update.
- A render skill is invoked but `profile.yaml` doesn't exist — block, run setup, then continue.

## The seven-step wizard

Each step has a clear input, a clear output, and a clear next step. Skip steps only when the prior step's output makes them unnecessary (e.g., skip extraction if the user supplied an existing template).

### Step 1 — Discovery

Ask one focused question:

> "What's your situation? **(a)** existing decks I can learn from, **(b)** an existing template I want to use, **(c)** both, or **(d)** I'm starting fresh."

Wait for the answer before proceeding.

- `(a)` → Steps 2-3 run extraction (loose decks → synthesized template). Step 4 (validation) runs against the synthesized output.
- `(b)` → Step 3 (extraction) is skipped. Step 4 (validation) runs against the user's supplied template.
- `(c)` → Both paths run. The synthesized template is the candidate; the supplied template is the reference; the user picks.
- `(d)` → Skip to Step 6 with the bundled neutral default template per format.

### Step 2 — Source intake

For each format the user cares about (pptx, figma — gslides comes in v0.2):

> "Point me at the [pptx file / Figma file key] for your [decks / template]."

Validate accessibility:

- **pptx**: file exists, has a `.pptx` extension, opens without error.
- **figma**: file key matches the format pattern; the Figma MCP returns metadata.

If validation fails, surface the specific error and re-prompt for a corrected source.

### Step 3 — Extraction *(skip if user supplied an existing template)*

For each source, invoke the per-format extractor sub-skill:

- pptx → `template-extractor-pptx`.
- figma → `template-extractor-figma`.

Each extractor emits a candidate template profile entry (layout_map, style_tokens, quality_score, findings). Surface the findings to the user, but don't ask for confirmation yet — extraction output feeds into validation.

### Step 4 — Validation

Run `template-validator` against the candidate (synthesized) or supplied template. The validator returns a structured findings report with green / yellow / red severities.

In v0.2, the validator implementation is full. In v0.1, the validator may be stubbed for some checks; the extractor's `_findings` are the primary signal.

### Step 5 — Quality report

Render a human-readable summary:

```
Template quality report — <format>

  Quality score: 88/100

  Green findings:
    - All 10 IR layout intents have a matching layout.
    - 8 color tokens extracted.

  Yellow findings:
    - 2 layouts use a different master than the rest. Consider consolidating.

  Red findings:
    - (none)

  → Accept and proceed?  [Y/n]
  → Or address findings first and re-run extraction?
```

If the user has yellow or red findings, give them the choice to address them in their source file and re-run extraction, or accept and proceed. Default to "accept."

### Step 6 — Preferred output

> "Which format do you want as your default render target? **(pptx / figma)**" *(gslides added in v0.2)*

The choice sets `profile.preferred_output`. Other formats remain available per-compile via explicit flag (e.g., `cowork run render-figma`).

If the user only configured one format in Steps 2-5, default `preferred_output` to that format and confirm.

### Step 7 — Persist

Assemble the profile and write to `~/.cowork/plugins/slide-publisher/profile.yaml`:

```yaml
profile_version: "1.0.0"
preferred_output: <pptx|figma>
templates:
  pptx:
    path: <user-supplied or extracted>
    layout_map: <from extractor or user-supplied>
    quality_score: <from validator>
  figma:
    file_key: <user-supplied>
    layout_map: <from extractor or user-supplied>
    template_map_json: <path to cached sidecar; populated on first render>
    quality_score: <from validator>
style_tokens:
  colors: { ... }
  typography: { ... }
voice_constraints: <user-supplied pointer if any; null otherwise>
setup_completed: <ISO date>
setup_version: <plugin version, e.g. 0.1.0>
```

Validate the written file against `template-profile/schema.json` before reporting success. On schema failure, surface the error and offer to re-run from Step 7 with corrected inputs.

Report:

> "Setup complete. Profile saved to ~/.cowork/plugins/slide-publisher/profile.yaml. You can now run `cowork run story-compiler` to produce an IR, then `cowork run render-pptx` (or render-figma) to publish."

## Edge cases

### Re-running setup over an existing profile

> "You already have a profile at ~/.cowork/plugins/slide-publisher/profile.yaml from <setup_completed>. **(a)** Update specific fields, **(b)** start over, **(c)** cancel."

For `(a)`, ask which fields and update in place. For `(b)`, archive the existing profile to `profile-<timestamp>.yaml` before overwriting, so it's recoverable. For `(c)`, exit cleanly.

### User has decks but no template

The most common case. Steps 2-3 do the work. Make sure the user understands: "I'm going to *infer* a template from your decks. You'll review the result before it's locked in."

### User has a template that's clearly broken

If the validator returns red findings (e.g., zero layouts matching IR intents), don't silently lock in a low-quality profile. Ask:

> "Your template has significant gaps — only 2 of 10 layouts matched. Renderers will fall back to 'nearest available' for the missing 8, which will be visible in the loss manifest. **(a)** Proceed anyway, **(b)** address the gaps in your template and re-run, **(c)** start with the bundled neutral default and migrate later."

### User supplies a figma file key but the Figma MCP isn't granted

> "The Figma MCP isn't connected. Grant it with `cowork plugin grant slide-publisher --mcp figma` and re-run setup."

Don't try to proceed without MCP access — the extractor needs it.

## What this skill is NOT

- Not a renderer. Setup produces the profile; rendering happens later via `render-pptx` or `render-figma`.
- Not a template editor. The wizard ingests and analyzes; it does not modify the user's source files.
- Not a one-shot autopilot. Each step asks for input or confirmation. Setup is a deliberate handshake between the plugin and the user's brand identity.

## Anonymity (plugin policy)

This skill ships in the public, anonymous plugin. No user data is hard-coded. The bundled neutral default template (`template-profile/default-template/`) is generic — no organization identity. The wizard runs entirely against the user's own inputs and writes only to the user's config directory.

## Composition with other skills

- `template-extractor-pptx`, `template-extractor-figma` — sub-skills invoked during Step 3.
- `template-validator` — sub-skill invoked during Step 4.
- `slide-ir-validator` — not used by setup. Runs at compile time / render time.
- `story-compiler` — not used by setup. Setup is a prerequisite, not a consumer.

## Reference

- Profile schema: `template-profile/schema.json`.
- Profile examples: `template-profile/examples/profile-pptx-only.yaml`, `profile-figma-only.yaml`.
- Default template (used when user has nothing): `template-profile/default-template/` *(populated in a later Day-2 / Day-3 task)*.
