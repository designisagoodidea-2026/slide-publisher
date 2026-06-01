> Summary: 11 lossless, 6 lossy, 6 dropped, 0 annotated.

# Loss manifest — Design system at 12 months: what worked, what didn't, what's next

- Rendered: 2026-06-01T22:26:49
- Renderer: `render-pptx`
- Template: `/sessions/jolly-nifty-cori/mnt/Slide Publisher/plugin/tests/validation/cases/case-02-weak-template/input.pptx`

## LOSSLESS (11)

- **deck-level / deck.title** — deck title applied to pptx core properties.
- **slide `title` / speaker_notes** — speaker notes (130 chars) preserved.
- **slide `where-we-started` / speaker_notes** — speaker notes (72 chars) preserved.
- **slide `the-headline` / speaker_notes** — speaker notes (137 chars) preserved.
- **slide `three-things-that-worked` / speaker_notes** — speaker notes (77 chars) preserved.
- **slide `the-consumption-gap` / speaker_notes** — speaker notes (93 chars) preserved.
- **slide `what-the-data-says` / speaker_notes** — speaker notes (127 chars) preserved.
- **slide `a-voice-from-the-field` / speaker_notes** — speaker notes (152 chars) preserved.
- **slide `what-next` / speaker_notes** — speaker notes (75 chars) preserved.
- **slide `the-callback` / speaker_notes** — speaker notes (70 chars) preserved.
- **slide `next-steps` / speaker_notes** — speaker notes (79 chars) preserved.

## LOSSY (6)

- **slide `three-things-that-worked` / layout_intent** — intent 'three_pillars' substituted to 'claim_with_evidence' (template layout 'Content with Caption') via the documented fallback chain.
- **slide `what-the-data-says` / layout_intent** — intent 'metrics' substituted to 'claim_with_evidence' (template layout 'Content with Caption') via the documented fallback chain.
- **slide `a-voice-from-the-field` / layout_intent** — intent 'quote' substituted to 'claim_with_evidence' (template layout 'Content with Caption') via the documented fallback chain.
- **slide `what-next` / layout_intent** — intent 'three_pillars' substituted to 'claim_with_evidence' (template layout 'Content with Caption') via the documented fallback chain.
- **slide `the-callback` / layout_intent** — intent 'callout' substituted to 'claim_with_evidence' (template layout 'Content with Caption') via the documented fallback chain.
- **slide `next-steps` / layout_intent** — intent 'callout' substituted to 'claim_with_evidence' (template layout 'Content with Caption') via the documented fallback chain.

## DROPPED (6)

- **deck-level / deck.audience** — 'audience' has no native .pptx representation; preserved only in the loss manifest (value: {'primary': 'Product + design leadership, post-adoption', 'secondary': ['Enginee).
- **deck-level / deck.throughline** — 'throughline' has no native .pptx representation; preserved only in the loss manifest (value: The system pays back when adoption is measured on consumption, not coverage — an).
- **deck-level / deck.arc** — 'arc' has no native .pptx representation; preserved only in the loss manifest (value: situation-first).
- **deck-level / deck.evidence_anchor** — 'evidence_anchor' has no native .pptx representation; preserved only in the loss manifest (value: hybrid).
- **deck-level / deck.duration_min** — 'duration_min' has no native .pptx representation; preserved only in the loss manifest (value: 25).
- **slide `title` / body_blocks** — layout has no body placeholders; 1 body block(s) were dropped.

