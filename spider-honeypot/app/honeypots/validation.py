"""
Consistency checks across the whole set of honeypot variant specs.

Each spec is validated by pydantic when it is created (see schemas.py).
This module checks the specs together: every failure mode from the
literature review must be targeted by at least one variant.
"""
from app.honeypots.schemas import FailureMode, HoneypotVariantSpec


class SpecValidationError(Exception):
    """Raised when a set of honeypot variant specs fails a design-consistency check."""


def validate_spec_set(specs: list[HoneypotVariantSpec]) -> None:
    """
    Raise SpecValidationError unless the specs, taken together, satisfy:

      1. Every variant_id is unique.
      2. Every spec targets at least one failure mode.
      3. Every known failure mode is targeted by at least one spec.
    """
    ids = [s.variant_id for s in specs]
    if len(ids) != len(set(ids)):
        duplicates = {i for i in ids if ids.count(i) > 1}
        raise SpecValidationError(f"Duplicate variant_id(s) found: {duplicates}")

    covered_modes: set[FailureMode] = set()
    for spec in specs:
        if not spec.target_failure_modes:
            raise SpecValidationError(f"{spec.variant_id} declares no target failure modes.")
        covered_modes.update(spec.target_failure_modes)

    missing = set(FailureMode) - covered_modes
    if missing:
        raise SpecValidationError(
            f"No variant in the spec set targets: {sorted(m.value for m in missing)}. "
            "Every failure mode should be covered by at least one honeypot variant."
        )