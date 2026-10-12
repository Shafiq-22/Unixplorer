"""Common result envelope for every physics model (CLAUDE.md §9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import astropy.units as u


class ModelDomainError(ValueError):
    """The inputs fall outside the model's validity domain (e.g. v >= c for sr_inertial)."""


@dataclass(frozen=True)
class ModelResult:
    model_id: str
    model_version: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    #: "physical" for named physical models; "speculative" for hypothetical_ftl_effective.
    status: str = "physical"

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form: Quantities become {"value", "unit"}; strings pass through."""
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "status": self.status,
            "inputs": {k: _encode(v) for k, v in self.inputs.items()},
            "outputs": {k: _encode(v) for k, v in self.outputs.items()},
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
        }


def _encode(value: Any) -> Any:
    if isinstance(value, u.Quantity):
        return {"value": float(value.value), "unit": value.unit.to_string()}
    return value
