# Git hooks

This directory holds the project's tracked git hooks. The repo root is the parent directory (the published plugin's root). After `git init` here, install with:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

## Hooks

- `pre-push` — anonymity check. Scans the working tree for forbidden tokens and blocks push on hits. See the script for the forbidden token list.

## Bypassing

`git push --no-verify` skips the hook. Do not bypass without intent — the hook exists to keep the public artifact anonymous.
