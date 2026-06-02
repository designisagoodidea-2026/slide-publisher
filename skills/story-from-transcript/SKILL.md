---
name: story-from-transcript
description: Convert a spoken transcript or long-form raw text into a Deck IR YAML. Use when the user has already said the thing — a recording transcript, a Zoom-call recap, a long-form essay, a meeting note — and wants slides that match. The skill identifies throughline, candidate beats, quotes, and metrics from the source, then assembles the IR shaped by the chosen storytelling style.
---

# story-from-transcript

Some users have the story already — they just don't have slides. Transcript-mode is the bridge from spoken/written long-form content to a Deck IR.

## When this skill triggers

- "Here's the transcript of my talk; turn it into slides."
- "I recorded myself thinking through this — make a deck."
- "Make slides from this Zoom recap."
- "Convert this essay into a presentation."
- The user pastes 500+ words of prose without an explicit outline structure.

## How to invoke

```bash
cowork run story-from-transcript --input my-talk.transcript.txt --style ted-talk --out my-talk.ir.yaml
```

Or pass the transcript directly in chat.

## How the skill processes the transcript

This skill is partly conversational, partly mechanical. Key steps:

### 1. Extract the throughline (mechanical)

Identify the most-repeated noun-phrase + verb-phrase pairing. Surface 2-3 candidates and ask the user to pick the one that matches their intent. The compiler refuses to fabricate the throughline — if the user can't pick a candidate, redirect to `story-from-interview`.

### 2. Segment into beats (mechanical + style-aware)

Cluster paragraphs by topic (basic semantic similarity). Map clusters to beat names per the style's beat catalog. For TED-talk, look for the hero's-journey arc — opening moment, problem, evidence, transformation, callback. For Tufte data, look for data-introduction → data-presentation → data-interpretation.

### 3. Identify body_block candidates

- **Quotes:** verbatim attributable text segments (often signposted by "said" or names in proximity).
- **Metrics:** numbers + units (e.g., "47%", "$8.2M").
- **Images:** the transcript can't supply images; flag spots where an image_placeholder would land and ask the user to provide alt text + intent.
- **Bullets:** ranked or enumerated lists in the source ("first... second... third...").

### 4. Honor the style's density rules

`reynolds-zen` will throw away dense paragraphs in favor of single-image slides; `tufte-data` will preserve every metric.

### 5. Surface the draft IR + ask for confirmation

Show the user the compiled IR before saving. Ask them to confirm or adjust:

- The throughline (most important — refuse to compile on disagreement).
- The arc (suggest from style + content).
- The beat order (suggest a default; let the user reorder).
- Per-slide body_blocks (the user may want to tighten or expand).

### 6. Validate + emit

Run `slide-ir-validator`. Save the IR. Save a `<deck>.source-transcript.txt` alongside for provenance.

## Refusal patterns

- Transcript < 200 words — too thin to extract a story from. Suggest `story-from-interview` or `story-from-outline`.
- Transcript has no clear throughline (mostly notes / brainstorm / lists) — ask the user to do a first pass at the throughline themselves.
- Transcript contains slides already (e.g., it's a copy of someone else's deck script) — redirect to `story-from-deck`.

## Style applies the way it does in `story-from-outline`

Same machinery — arc validation, beat allocation, density enforcement, layout-intent priors. See `story-from-outline/SKILL.md` § "How the style is applied."

## Composition

- **Upstream:** `storytelling-style-library` resolves the style.
- **Downstream:** any renderer.
- **Sibling:** `story-from-interview` when transcript is too thin.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md). The user's transcript may contain proprietary content; the skill processes it locally and never sends it outside the user's session.

## Reference

- IR schema: `ir/schema.json`.
- Style schema: `styles/schema.json`.
