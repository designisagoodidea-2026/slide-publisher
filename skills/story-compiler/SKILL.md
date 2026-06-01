---
name: story-compiler
description: Compile a story outline (audience, throughline, beats, evidence) into a Deck IR YAML that the slide-publisher renderers consume. Use this skill whenever the user wants to turn a written outline, talk-track sketch, or story scaffold into structured slide content — even if they say "draft my deck," "make slides from this outline," "build a presentation structure," or "convert my notes into slides." Outline-mode only in v0.1. Refuses to draft when audience, throughline, or evidence anchor is missing — asks instead.
---

# story-compiler

Turn a hand-authored story outline into a validated Deck IR YAML. The IR is the durable, renderer-agnostic representation of a deck — every downstream renderer (pptx, figma, eventually gslides) reads it.

## When this skill triggers

Trigger when the user wants to compile a story into slide structure. Common phrasings:

- "Draft a deck from this outline."
- "Turn my notes into slides."
- "Compile this story into IR."
- "Build the structure for a 20-minute talk on X."
- "Convert this design-review outline into a deck."

Also trigger when the user has provided an outline-shaped markdown document and is clearly expecting slides as the next step, even if they don't name "compiler" or "IR." The outline-shape signal: a frontmatter or labeled section listing audience, throughline, beats, evidence — or a structured prose outline with H2/H3 sections matching the beat catalog.

## What this skill is NOT

- Not a slide-design tool. The IR specifies *intent* per slide (`layout_intent: claim_with_evidence`), not pixel positions. Visual polish is the renderer's and template's job.
- Not a one-shot generator from a vague prompt. If audience / throughline / evidence anchor is missing, the skill refuses to draft and asks.
- Not transcript- or case-study-mode in v0.1 — those modes are scoped for v0.2. If the user pastes a recording transcript or a project dossier, surface that v0.2 covers it and either accept an outline conversion or stop.

## Required inputs (outline-mode contract)

The outline must supply:

1. **Audience** — `primary` (role + stage) and `prior_knowledge` (cold / warm / informed / expert). `secondary` audiences optional but encouraged.
2. **Throughline** — the one sentence the audience leaves with. The throughline is the deck's contract with itself; every slide either advances it, supports it, or callbacks to it.
3. **Arc** — one of `problem-first`, `situation-first`, `provocation`, `case-led`, `reverse-chronological`. If the user names a different arc, ask whether it maps to one of these or whether they want a v0.2 catalog expansion.
4. **Evidence anchor** — one of `numbers`, `story`, `demo`, `framework`, `hybrid`. This is the primary kind of evidence the deck rests on. It informs which `layout_intent` lands in evidence beats.
5. **Beats** — an ordered list of narrative beats. Each beat names the slide's role (`hook`, `context`, `problem`, `claim`, `evidence`, `tension`, `resolution`, `callback`, `next`) and the slide's content.
6. **Duration** — optional but recommended. Used to pace slide count vs. content density.

If any of audience / throughline / evidence anchor is missing, do not draft. Ask one focused question per missing field and wait. Never invent these — a deck without a throughline is a deck without a point.

## Output: the Deck IR

Output is a single YAML file conforming to `ir/schema.json` (JSON Schema 2020-12). The shape:

```yaml
ir_version: "1.0.0"

deck:
  title: <string>
  audience:
    primary: <string>
    secondary: [<string>, ...]   # optional
    prior_knowledge: <cold|warm|informed|expert>
  throughline: <string>
  arc: <problem-first|situation-first|provocation|case-led|reverse-chronological>
  duration_min: <int>            # optional, 1-240
  evidence_anchor: <numbers|story|demo|framework|hybrid>
  voice_constraints: <string>    # optional pointer to user-supplied voice spec

slides:
  - id: <kebab-case-string>
    beat: <hook|context|problem|claim|evidence|tension|resolution|callback|next>
    layout_intent: <one of 10 below>
    title: <string>
    body_blocks:                 # optional
      - kind: <prose|bullets|metric|quote|image_placeholder|diagram_placeholder>
        content: <type depends on kind — see below>
    speaker_notes: <string>      # recommended on claim/evidence/tension/resolution beats
    transitions:                 # optional
      from_prior: <string>
      to_next: <string>
```

See `ir/schema.json` for the authoritative structure, `ir/examples/*.yaml` for three full hand-authored examples that double as test fixtures.

### Layout intents (10 in v0.1)

`title`, `section_break`, `claim_with_evidence`, `three_pillars`, `comparison`, `quote`, `image_with_caption`, `metrics`, `timeline`, `callout`.

The catalog is intentionally small — adding intents is a scoping pass, not a configuration. Pick the closest fit; if nothing fits, fall back to `claim_with_evidence` (the universal default) and note the awkwardness in `speaker_notes`.

### Body block kinds (6 in v0.1)

| kind | content shape | Use for |
|---|---|---|
| `prose` | string | Free-flowing supporting text. |
| `bullets` | array of strings | Lists, pillars, ranked items. |
| `metric` | `{label, value, unit?, comparison?}` | A single anchored number. |
| `quote` | `{text, attribution?}` | A pull quote from research / interview / customer. |
| `image_placeholder` | `{alt, intent}` | A real image the renderer should leave a slot for. Intent describes what the image should show. |
| `diagram_placeholder` | `{alt, intent}` | A diagram (chart, flow, etc.) the renderer leaves space for. |

`image_placeholder` and `diagram_placeholder` do not generate images. They reserve space and document intent. Image and diagram generation is a v0.3 surface.

## Process — outline → IR

1. **Read the outline end-to-end.** Confirm all required fields are present. If not, ask.
2. **Identify the deck title.** If not stated, propose one anchored on the throughline + audience and confirm before writing.
3. **Infer the arc** if not stated. The four-question diagnostic: who is the audience, what does the throughline ask of them, what do they already know, and what evidence do you have? Map to one of the five arcs. Confirm with the user if the inference is non-obvious.
4. **Allocate slides per beat.** A 20-minute deck is typically 12-18 slides; a 5-minute deck is 5-8. Beat density follows the arc:
   - `problem-first`: more time on problem and tension; resolution lands late.
   - `situation-first`: more time on context; problem and claim land mid-deck.
   - `provocation`: hook is the headline; rest of deck unpacks why.
   - `case-led`: evidence beats dominate; claim emerges from the evidence.
   - `reverse-chronological`: timeline-driven; beats reverse-narrate from outcome to origin.
5. **Map each beat to a `layout_intent`.** Use the table below as a starting point; deviate only with reason.
6. **Populate body_blocks** from the outline content. If the outline gives prose, prefer `prose`. If it gives a ranked list, prefer `bullets`. If it cites a number, prefer `metric`. If it cites a person, prefer `quote`.
7. **Draft `speaker_notes`** for at least every `claim`, `evidence`, `tension`, and `resolution` slide. These slides do real narrative work; missing notes is a `slide-ir-validator` lint hit.
8. **Add `transitions.from_prior` and `to_next`** when a slide's connection to its neighbors isn't obvious from the titles alone.
9. **Validate.** Run `slide-ir-validator` against the output before handing back. If validation fails, fix and re-run.

### Beat → layout-intent mapping (default)

| Beat | Default layout intent | Alternatives | Notes |
|---|---|---|---|
| `hook` | `title` or `callout` | `quote`, `provocation`-style `callout` | Opens the deck. One sentence, sometimes paired with the title slide. |
| `context` | `claim_with_evidence` | `timeline`, `metrics`, `section_break` | Sets scene. Often where the situation lands. |
| `problem` | `claim_with_evidence` | `comparison`, `metrics`, `callout` | The friction. Named clearly. |
| `claim` | `claim_with_evidence` | `callout`, `three_pillars` | The throughline restated. |
| `evidence` | varies by `evidence_anchor` | `metrics` (if `numbers`), `quote` (if `story`), `timeline` (if `framework`), `image_with_caption` (if `demo`) | The deck's proof surface. |
| `tension` | `comparison` | `claim_with_evidence`, `metrics` | What's at stake; what changes if nothing changes. |
| `resolution` | `three_pillars` | `claim_with_evidence`, `callout` | The fix. Often three concrete moves. |
| `callback` | `callout` | `quote` | Echoes the throughline. Often slide N-1. |
| `next` | `callout` | `timeline`, `claim_with_evidence` | Concrete next step + owner + date. Last slide. |

## Refusal patterns

Refuse to draft, and ask, when:

- **Audience is "everyone" or unstated.** A deck for everyone is a deck for no one. Ask who the *primary* audience is — role + stage. Don't accept "leadership" alone; ask "VP of what, at what stage."
- **Throughline is vague or aspirational** (e.g. "we should be more strategic"). Ask the user to compress it to one sentence that an audience member could *quote back* after the deck. If they can't, the deck isn't ready to compile.
- **Evidence anchor is missing.** Without an anchor, slides become generic. Ask "what kind of evidence are you anchored on" with the five options.
- **Outline has no beats.** Without beats, there's nothing to allocate to slides. Ask for at least 5-7 beats in narrative order.

Don't refuse on missing arc — infer it and confirm. Don't refuse on missing duration — default to 15 minutes and flag.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).


## Examples

See `ir/examples/`:

- `design-system-retro.yaml` — 10 slides, `situation-first` arc, `hybrid` evidence anchor. Exercises `claim_with_evidence`, `three_pillars`, `comparison`, `metrics`, `quote`, `callout`.
- `product-launch-readout.yaml` — 9 slides, `problem-first` arc, `numbers` evidence anchor. Exercises `timeline`, `comparison`, `metrics`, `image_with_caption`, `quote`, `callout`.
- `executive-briefing.yaml` — 12 slides, `provocation` arc, `framework` evidence anchor. Exercises `section_break`, `three_pillars`, `image_with_caption`, `callout`, `diagram_placeholder`.

Read these to ground the compiler's instinct for slide density, body-block selection, and speaker-notes voice. Do not copy their content into a new deck — they are generic fixtures, not templates for real-world delivery.

## When to push back instead of compile

- The user wants a 60-slide deck for a 15-minute talk. Push back: tighter throughline, fewer slides.
- The user wants the deck before they've decided what the audience should walk away with. Push back: write the throughline first.
- The user wants to "see what you come up with" with no inputs. This is the "generic outputs" trap. Refuse and ask for at least audience + throughline + one evidence anchor before drafting.
