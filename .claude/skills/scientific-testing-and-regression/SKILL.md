---
name: scientific-testing-and-regression
description: Rules for the release-blocking physics regression suite (tests/scientific) and other numerical tests. Use when adding a model, changing numerics, or touching frames/distances.
---

# Scientific testing and regression

- `uv run pytest tests/scientific` is release-blocking and runs in CI on every change.
- Assert closed forms against the formula, with the distance as a test input, at `rel=1e-9`
  or tighter.
- Check CLAUDE.md §10 table values only at the precision the table quotes them. If the table
  and the formula disagree, report it; never loosen a tolerance to make it pass.
- State every tolerance next to the assertion. A loose tolerance needs a comment saying why,
  for example an integrator step or a quoted precision.
- Test domain edges explicitly: v = 0, v = c and v > c for each model, plus the refusal paths
  (`ModelDomainError`, and `TypeError` for bare floats).
- Frames: compare against astropy's own transform, and check that heliocentric and
  galactocentric separations agree to 1e-9 relative.
- Test values are inputs, not measurements. Label them so, and never present them as
  catalogue data.
- A TypeScript port of a formula is tested against fixtures exported from Python, never
  against values typed in by hand.
