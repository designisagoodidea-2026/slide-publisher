---
name: storytelling-style-library
description: Manage the user's storytelling styles. Use whenever the user wants to "see what styles are available," "pick a storytelling style," "create my own style," "validate my style," or "switch the deck's storytelling style." Lists built-in styles, surfaces their descriptions, validates user-authored styles against the schema, and merges parent styles via the `extends:` field.
---

# storytelling-style-library

A storytelling style is a complete configuration of arc choice, beat allocation, density rule, posture, and layout-intent priors. This skill helps the user discover, validate, and author styles.

## When this skill triggers

- "Which storytelling styles can I pick?"
- "Show me the styles."
- "Create a custom style based on TED talk but with more evidence slides."
- "Validate my style file."
- "Switch my deck to mckinsey-pyramid."

## How to invoke

List built-in + user styles:

```bash
cd "<plugin-root>"
ls styles/*.yaml
ls ~/.cowork/plugins/slide-publisher/styles/*.yaml 2>/dev/null
```

Validate a user-authored style against the schema:

```bash
cd "<plugin-root>"
python3 -c "
import json, yaml, sys
from jsonschema import Draft202012Validator
schema = json.loads(open('styles/schema.json').read())
doc = yaml.safe_load(open(sys.argv[1]).read())
errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
if errors:
    [print(f'{list(e.path)}: {e.message}') for e in errors]
    sys.exit(1)
print('OK')
" /path/to/my-style.yaml
```

## Style precedence

1. User styles in `~/.cowork/plugins/slide-publisher/styles/*.yaml` win over plugin-shipped styles of the same name.
2. A style with `extends: <parent-name>` merges: parent first, then its own keys override.

## The 8 starter styles

See `styles/README.md` for the table. Quick summary:

- **`ted-talk`** — Hero's Journey, audience-as-hero, low density. Inspirational talks.
- **`duarte-sparkline`** — What-is/what-could-be contrast. Vision + persuasion.
- **`reynolds-zen`** — One idea per slide; image + phrase only. Spoken delivery.
- **`tufte-data`** — Show the data; high density. Research readouts.
- **`mckinsey-pyramid`** — Pyramid Principle; three reasons. Executive briefings.
- **`case-study-star`** — Situation/Task/Action/Result. Portfolio cases.
- **`executive-briefing-provocation`** — Provocation arc. Strategy decks.
- **`default-balanced`** — Middle-of-the-road. When you don't know which to pick.

## Composition with other skills

- **Upstream:** none. This skill is reference + management.
- **Downstream:** all four `story-from-*` skills accept a `--style <name>` flag that resolves through this library.

## What this skill is NOT

- Not a compiler. Styles only configure the compiler.
- Not a renderer. Styles influence beat → layout_intent priors, but the renderer's profile-side layout_map still resolves to actual layouts.

## Reference

- Schema: `styles/schema.json`.
- Library README: `styles/README.md`.
