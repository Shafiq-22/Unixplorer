"""Universe Atlas physics source of truth (CLAUDE.md §4, §7, §9).

Every public function takes astropy Quantities, never bare floats, and every travel model
returns a `ModelResult` naming its model, version, inputs, outputs, assumptions and warnings.
"""

from astronomy_core.result import ModelDomainError, ModelResult

__all__ = ["ModelDomainError", "ModelResult"]
