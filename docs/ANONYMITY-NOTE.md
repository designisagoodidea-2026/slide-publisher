# Anonymity note

Referenced from every skill in this plugin. Save space by linking here instead of restating in each `SKILL.md`.

## What this plugin ships with

Generic defaults only. No personal names, no organization references, no industry-specific patterns.

- Default palette and typeface (Inter + neutral brand-shaped colors) used by remediation skills when the user's file has zero tokens.
- Heuristic pattern dictionaries (`INTENT_PATTERNS`, `INTENT_TO_HEURISTIC_NAME`) derived from generally-applicable English-language slide-deck conventions.
- Synthetic example IRs in `ir/examples/` use fictional companies and stories.

## What gets enforced at the repo boundary

A pre-push hook at `plugin/.githooks/pre-push` scans every commit for forbidden tokens (personal names, the maintainer's full email address). The hook blocks pushes on hits. See `STAGING.md` (internal doc, not in repo) for the project's anonymity-rule reference.

## What's user-supplied

Every skill that produces output works against user inputs only — the user's templates, the user's files, the user's MCP credentials, the user's voice spec (optional). The plugin never bundles real-world content.

## In skills

When a skill needs to mention this posture, link to this file rather than restating:

```markdown
## Anonymity

See `docs/ANONYMITY-NOTE.md`.
```

That's the entire section.
