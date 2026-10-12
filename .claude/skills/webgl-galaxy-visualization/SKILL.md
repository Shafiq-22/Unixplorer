---
name: webgl-galaxy-visualization
description: Rules for the React Three Fiber 3D view: floating origin, log depth, tile LOD, illustrative labels, accessibility. Use when editing apps/web/src/components/GalaxyView.tsx or anything rendered in 3D.
---

# WebGL galaxy visualisation

- **Client-only R3F:** `GalaxyView` is loaded through `next/dynamic` with `ssr: false`.
- **Scene and precision:** scene units are parsecs. Positions stay float64 (JS numbers) until
  `rebase()` subtracts the focus point; only those camera-relative offsets become float32.
  - Use `relative()` for small lines and markers.
- **Depth:** `logarithmicDepthBuffer: true`, near 1e-9 pc, far 1e5 pc. Check for jitter when
  focusing on Earth, Proxima and Sgr A* (M3/M4).
- **Loading:** stars load as octree tiles: level 0 (brightest) plus the level-2 neighbourhood
  of the focus. Never fetch the whole catalogue.
- **Labelling:** sizes, brightness and colours not computed from a named model carry a
  persistent `Illustrative` label (§5). The disc and arm backdrop (M4) must be labelled
  illustrative too.
- **No physics in the UI:** the ship position is `lerp3(origin, destination, fraction)`, where
  `fraction` comes from backend trajectory samples via `viewAt`.
- **Accessibility:** every 3D interaction needs a keyboard or search alternative (focus and zoom
  buttons, the search combobox). Respect `prefers-reduced-motion`: no damping, no animated
  camera moves.
- **Verify visually:** after a change, take a Playwright screenshot. A passing E2E does not
  prove the canvas has a size.
- **Labels:** body labels use drei `<Html>` with `portal={labelLayer}`, a fixed overlay div.
  Without it, drei mounts the first label before its default target settles and leaves it
  empty (seen in M3).
  - Overlapping bodies share one label (`lib/labels.ts`).
  - Labels only show below about 0.002 pc camera distance.
- **Zoom:** zoom buttons update the readout themselves; OrbitControls only reports wheel and
  drag changes. Camera distance ranges from `MIN_VIEW_PC` (2e-9) to `MAX_VIEW_PC` (2000).
- **Test exit codes, not grep output:** `pnpm test | grep Tests` hid a test file that failed
  to load.
