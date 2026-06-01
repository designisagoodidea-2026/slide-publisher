---
name: iterate-to-parity
description: Iterate the render → visual-diff → adjust loop until output visually matches the input reference, or max_iterations is hit. Use this skill when the user has a reference deck (any format) and wants the rendered output to look close to it. Closes the rendering loop — first pass might not match, iteration converges.
---

# iterate-to-parity

Convergence loop: render with current profile → diff against reference → diagnose lowest-parity slide → adjust profile → re-render. Stops at the parity target (default SSIM ≥ 0.85) or max_iterations (default 5).

## How to invoke

```bash
cd "<plugin-root>"
python adapters/iterate_to_parity.py \
  --input-pngs ref-01.png ref-02.png ... \
  --ir my-deck.ir.yaml \
  --profile starting-profile.yaml \
  --out-dir /tmp/iterate/ \
  --max-iterations 5 \
  --parity-target 0.85
```

Each iteration lands in `/tmp/iterate/iter-NN/` with:

- `profile.yaml` — the profile state for that iteration.
- `rendered.pptx` — the render output.
- `diff/` — visual-diff outputs.

stdout: structured iteration log (JSON) with per-iteration aggregate parity + adjustment applied + status.

## v0.1 adjustments

The diagnoser identifies the lowest-parity slide; the adjuster swaps that slide's `layout_intent` mapping to the next-best alternative in the documented fallback chain (same chain the renderer uses).

Termination conditions:

- **Converged** — aggregate parity ≥ target.
- **Exhausted adjustments** — no more fallbacks for the offending intent.
- **No diagnosis possible** — diff produced no actionable signal (e.g., zero slides matched).
- **Max iterations** — gave up cleanly.

## v0.2 expansions

- Style-token adjustments (color drift → palette refinement; font drift → typeface swap).
- Per-slide layout overrides (not whole-profile changes).
- Adaptive parity target per slide (some slides are inherently harder to match).
- Cost-aware adjustment ordering (prefer cheap changes first).

## Composition

- **Upstream:** any input adapter for the reference PNGs; `story-compiler` for the IR; `template-setup` for the starting profile.
- **Downstream:** the final iteration's rendered.pptx is the output the user keeps.

## When NOT to use

- The reference and the IR represent fundamentally different stories — no rendering can match. Diagnose by inspecting iter-01/diff.html.
- The starting profile is empty / invalid — fix that first via `template-setup`.

## Reference

- Adapter: `adapters/iterate_to_parity.py`.
- Diagnostic loop: read the source for the heuristic adjustment logic.
