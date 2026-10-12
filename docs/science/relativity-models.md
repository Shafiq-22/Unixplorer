# Travel-time models

Code: `packages/astronomy-core/astronomy_core/relativity.py`. Tests: `tests/scientific/test_relativity.py`.

Every model returns a `ModelResult` with `{model_id, model_version, status, inputs, outputs,
assumptions[], warnings[]}`. All models assume flat spacetime, static endpoints and a
straight-line path. These assumptions are listed in every result, not left implicit.

| `model_id` | Domain | Outputs | Refuses |
|---|---|---|---|
| `classical_constant_speed` | any v > 0 | coordinate time D/v | v ≤ 0. Warns when v > 0.1c and when v ≥ c |
| `sr_inertial` | massive, 0 < v < c | γ, Δt = D/v, Δτ = Δt/γ | v ≥ c |
| `sr_constant_proper_accel` | massive, a > 0, flip at midpoint | Δt, Δτ, peak γ, peak v; plus `sr_constant_proper_accel_state` for x, v and τ at any t | a ≤ 0 |
| `null_propagation` | v = c | light-travel time D/c; proper time "not defined" | — |
| `hypothetical_ftl_effective` | v_eff > c, status `speculative` | t_eff = D/v_eff; proper time "not defined by this model" | v_eff ≤ c |

Formulas for constant proper acceleration, flipping at the midpoint:

- Δτ = (2c/a)·arcosh(1 + aD/(2c²))
- Δt = (2c/a)·sinh(aΔτ/(2c))
- peak γ = 1 + aD/(2c²)

Each phase uses the hyperbolic-motion state, and the deceleration phase mirrors the
acceleration phase in time.

Constants come from astropy: `c`, standard gravity `g0` = 9.80665 m/s², and the Julian year
(`u.yr`, 365.25 d). Physics signatures take Quantities only and raise `TypeError` for bare
floats.
