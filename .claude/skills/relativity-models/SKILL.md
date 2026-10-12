---
name: relativity-models
description: How to add or change a travel-time physics model in astronomy-core (classical, special relativity, null, speculative FTL). Use for any change to relativity.py, model outputs, or the result envelope.
---

# Relativity models

1. Physics lives only in `packages/astronomy-core/astronomy_core/`. The API and UI call it and
   never re-implement a formula.
2. One code path per `model_id` (CLAUDE.md §9). Never reuse γ or proper time outside
   `sr_inertial` and `sr_constant_proper_accel`.
3. Validate the domain at the entry point and raise `ModelDomainError`. Never clamp an input:
   v ≥ c is refused by SR models, and v ≤ c by the FTL model.
4. Return a `ModelResult`. Bump `model_version` whenever outputs could change for the same
   inputs, because stored routes are reproduced by `(model_id, model_version)`.
5. List every simplification in `assumptions`. Start from `COMMON_ASSUMPTIONS` (flat spacetime,
   static endpoints, straight path) and never drop one silently.
6. Speculative models set `status="speculative"` and claim no mechanism or causality.
7. Inputs and outputs are astropy Quantities. Constants come from `astronomy_core.constants`
   (astropy), never typed in.
8. Add or extend `tests/scientific`, following the `scientific-testing-and-regression` skill,
   in the same change.
