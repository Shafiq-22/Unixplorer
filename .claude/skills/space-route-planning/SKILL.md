---
name: space-route-planning
description: Routes and traversals end to end: POST /routes (all models side by side), trajectories, traversal sessions and the frame-rate-independent UI clock. Use when changing route_planner, routes.py, RoutePlanner/TraversalPanel, or traversalClock.ts.
---

# Space route planning

- **One route, every model:** `route_planner.plan.plan` runs every §9 model on one route and
  also evaluates each at the distance-range bounds.
  - Out-of-domain inputs give a `refused` entry with the model's reason. Never clamp a speed
    (v ≥ c is refused by the SR models; v ≤ c by the FTL model).
- **Assumptions:** every entry carries the model's assumptions plus `ROUTE_ASSUMPTIONS` (epochs,
  no proper motion over the trip).
- **Persistence:** routes are stored in `route_calculation` with the parameters, distance range,
  endpoints, full model results, `frame_metadata()` and `code_version`, so they are
  reproducible.
- **Trajectories:** `trajectory()` returns backend-computed samples (coordinate time, proper
  time or null, fraction, speed). The UI interpolates linearly and never re-implements a
  formula.
- **Traversals:** sessions follow `TRANSITIONS` (planned/running/paused/cancelled/arrived).
  Anything else returns 409.
- **UI clock:** the only state is the simulated coordinate time, advanced by wall-clock deltas
  (`advance`). It must give the same state at 16 ms and 100 ms ticks; that test is in
  `traversalClock.test.ts`.
- **Speculative labelling:** speculative results show the `Speculative` badge everywhere they
  appear (table and traversal panel).
- **E2E:** `apps/web/e2e/m2-solar-neighbourhood.spec.ts` covers search, dossier, route,
  travel, pause, resume and cancel.
