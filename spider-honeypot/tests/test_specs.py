"""Unit tests for the honeypot design schemas, specs and validation."""
import pytest
from pydantic import ValidationError

from app.honeypots.schemas import (
    DynamicLinkGraphTrapSpec,
    FailureMode,
    PromptInjectionTrapSpec,
)
from app.honeypots.specs import ALL_VARIANT_SPECS
from app.honeypots.validation import SpecValidationError, validate_spec_set


def test_all_concrete_specs_exist():
    assert len(ALL_VARIANT_SPECS) == 3


def test_spec_set_covers_all_failure_modes():
    # Should not raise: the three specs together target semantic_evaluation,
    # policy_aware_reasoning and multimodal_rendering.
    validate_spec_set(ALL_VARIANT_SPECS)


def test_spec_set_rejects_duplicate_ids():
    duplicated = ALL_VARIANT_SPECS + [ALL_VARIANT_SPECS[0]]
    with pytest.raises(SpecValidationError):
        validate_spec_set(duplicated)


def test_spec_set_detects_missing_failure_mode_coverage():
    only_without_policy_mode = [
        s for s in ALL_VARIANT_SPECS if FailureMode.POLICY_AWARE_REASONING not in s.target_failure_modes
    ]
    with pytest.raises(SpecValidationError):
        validate_spec_set(only_without_policy_mode)


def test_prompt_injection_template_requires_canary_placeholder():
    reference = next(s for s in ALL_VARIANT_SPECS if s.variant_id == "prompt-injection-trap-v1")
    with pytest.raises(ValidationError):
        PromptInjectionTrapSpec(
            variant_id="bad-injection",
            name="bad",
            description="bad",
            concealment_strategy=reference.concealment_strategy,
            target_failure_modes=[FailureMode.SEMANTIC_EVALUATION],
            target_modality=reference.target_modality,
            fidelity_level=reference.fidelity_level,
            honeytoken_type=reference.honeytoken_type,
            acceptance_criterion="x",
            injection_surface="html_comment",
            injected_instruction_template="no placeholder here",
            expected_side_effect="canary_in_output",
        )


def test_dynamic_graph_template_requires_placeholders():
    reference = next(s for s in ALL_VARIANT_SPECS if s.variant_id == "dynamic-graph-trap-v1")
    with pytest.raises(ValidationError):
        DynamicLinkGraphTrapSpec(
            variant_id="bad-graph",
            name="bad",
            description="bad",
            concealment_strategy=reference.concealment_strategy,
            target_failure_modes=[FailureMode.SEMANTIC_EVALUATION],
            target_modality=reference.target_modality,
            fidelity_level=reference.fidelity_level,
            honeytoken_type=reference.honeytoken_type,
            acceptance_criterion="x",
            max_depth=5,
            teaser_template="missing placeholders",
            termination_condition="max_depth_reached",
        )


def test_spec_requires_at_least_one_failure_mode():
    reference = next(s for s in ALL_VARIANT_SPECS if s.variant_id == "semantic-trap-v1")
    with pytest.raises(ValidationError):
        reference.__class__(
            variant_id="bad-semantic",
            name="bad",
            description="bad",
            concealment_strategy=reference.concealment_strategy,
            target_failure_modes=[],
            target_modality=reference.target_modality,
            fidelity_level=reference.fidelity_level,
            honeytoken_type=reference.honeytoken_type,
            acceptance_criterion="x",
            content_topic="x",
            content_generation_strategy="x",
        )