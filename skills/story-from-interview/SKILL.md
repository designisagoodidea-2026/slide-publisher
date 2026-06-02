---
name: story-from-interview
description: Elicit a story interactively by asking the user a series of focused questions tailored to the chosen storytelling style, then assemble the answers into a Deck IR YAML. Use whenever the user doesn't have an outline yet but wants to talk through what they're trying to say — "help me figure out what to say," "interview me about this talk," "I don't know where to start, just ask me questions."
---

# story-from-interview

When the user doesn't have an outline yet — and may not have a clear story yet — the interview skill walks them through eliciting one. Questions are style-aware: a TED-style interview opens differently than a Tufte data interview.

## When this skill triggers

- "I have something to say but I don't know how to structure it."
- "Just ask me questions and we'll build it from there."
- "Interview me about this case study."
- The user pastes raw thinking + says "help me make sense of this."

Often follows `template-setup` when the user has no IR yet.

## How the skill works

This is a **conversational** skill. No Python adapter. The skill drives a back-and-forth in the Cowork chat, asks one focused question per turn, and accumulates the answers into the IR.

### Pacing rule

**One question per turn.** Do not flood the user. Each question's answer informs the next question.

### Style affects the question sequence

The skill loads the chosen style (`style: <name>` in user's request, or `default-balanced`). Each style has a recommended interview sequence — when authoring a new style, encode this in the style's `voice_notes` or a sibling file. For the 8 starter styles, use the sequences below.

#### TED-talk sequence (Hero's Journey)

1. Who is your audience? (role + stage + what they already believe)
2. What's the one thing you want them to leave knowing or doing? (throughline)
3. In one sentence, what's the world like for them today? (ordinary world)
4. What's about to change for them — or what could change if they acted? (call to adventure)
5. What's the hardest part of that change? Why don't they just do it? (trials)
6. What does the better world look like — concretely? (transformation)
7. What's their first step tomorrow morning? (return / next)

#### Tufte data sequence

1. What's the dataset you're presenting?
2. What's the one number that matters most? (the headline metric)
3. What's the timeframe and population?
4. What surprised you in the data?
5. What's the methodological caveat the audience needs to know?
6. What action does the data support (or undermine)?
7. What follow-up analysis would resolve open questions?

#### McKinsey pyramid sequence

1. What's the recommendation in one sentence?
2. What are the three reasons it's right?
3. For each reason, what's the supporting evidence?
4. What's the strongest counter-argument?
5. What's the implementation cost + timeline?
6. What's the kill criteria — when would you walk away?
7. What's the decision you need from this audience?

#### Reynolds Zen sequence

1. What's the audience's emotional state when you start speaking?
2. What's the one image or moment they should carry away?
3. What story (anecdote, customer, person) makes the point concrete?
4. What does the change look like felt rather than measured?
5. What single phrase captures the takeaway?
6. What's their first felt action?

#### Other styles

For `duarte-sparkline` and `case-study-star`, use the structure inherent in the framework (sparkline alternates "what is" / "what could be"; STAR walks Situation / Task / Action / Result). For `default-balanced`, fall back to the TED-talk sequence with less rhetorical commitment.

### After all answers are collected

1. Assemble the answers into the deck-level IR fields (`audience`, `throughline`, `arc`, `evidence_anchor`).
2. Allocate slides per beat per the style's `beats.<beat>.min/max` and `density.slides_per_minute × duration_min`.
3. Pre-populate slide titles + body_blocks from the user's answers.
4. Emit the IR YAML.
5. Run `slide-ir-validator` and surface any findings.
6. Tell the user what comes next: render-pptx or render-figma.

## Refusal patterns

- If the user gives one-word answers across multiple questions, slow down. Ask the next question more concretely. Don't push to compile a half-empty IR.
- If the user changes the topic mid-interview, save what we have, ask if they want to start over or continue with both threads.
- If the user wants to skip the interview and just provide the IR, redirect to `story-from-outline`.

## Output

A Deck IR YAML conforming to `ir/schema.json`. Same shape as `story-from-outline`'s output. Plus an interview log saved alongside (`<deck>.interview.md`) capturing the Q&A — useful for revision later.

## Composition

- **Upstream:** `storytelling-style-library` resolves the style.
- **Downstream:** any renderer.

## Anonymity

See [`docs/ANONYMITY-NOTE.md`](../../docs/ANONYMITY-NOTE.md).
