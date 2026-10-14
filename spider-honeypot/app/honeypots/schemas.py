"""
Pydantic schemas describing the design of each honeypot variant.

The schemas record the design decisions in a form that can be validated
and tested. They hold no page content or routing; that lives in
app/honeypots/content.py and app/honeypots/routes.py.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class FailureMode(str, Enum):
    """
    Reasons, identified in the literature review, why traditional spider
    honeypots fail against LLM-driven agents. Each variant declares which
    of these it targets.
    """

    SEMANTIC_EVALUATION = "semantic_evaluation"
    """The agent judges a page's value before following a link, so a sparse
    or meaningless trap page gets skipped."""

    POLICY_AWARE_REASONING = "policy_aware_reasoning"
    """The agent reasons about robots.txt rather than simply obeying or
    ignoring it, and can recognise when an entry is shielding a honeypot."""

    MULTIMODAL_RENDERING = "multimodal_rendering"
    """Vision-language agents see a page as a person would, so they rarely
    interact with links that exist only in the DOM."""


class FidelityLevel(str, Enum):
    """Interaction level of the honeypot."""

    LOW = "low_interaction"
    MEDIUM = "medium_interaction"
    HIGH = "high_interaction"


class ConcealmentStrategy(str, Enum):
    """
    How a trap stays out of sight of human users while remaining reachable
    by an agent. CSS hiding is deliberately not an option, because
    vision-based agents can see through it.
    """

    UNLINKED_SITEMAP_ENTRY = "unlinked_sitemap_entry"
    ORPHANED_API_ENDPOINT = "orphaned_api_endpoint"
    ROBOTS_DISALLOWED_PATH = "robots_disallowed_path"
    BURIED_INTERNAL_LINK = "buried_internal_link"


class HoneytokenType(str, Enum):
    """A unique string used as an independent signal that an agent saw the content."""

    FAKE_EMAIL = "fake_email"
    """Not used by any variant in this project. A synthetic email adds privacy
    questions without any benefit over a document ID or canary string. If one
    is ever needed, use a non-deliverable domain such as .invalid."""
    FAKE_DOCUMENT_ID = "fake_document_id"
    CANARY_STRING = "canary_string"
    NONE = "none"


class TargetModality(str, Enum):
    """How the targeted agent perceives the page."""

    TEXT_EXTRACTION = "text_extraction"
    """Agents that read the DOM or markdown, such as Crawl4AI."""

    VISION_RENDERING = "vision_rendering"
    """Agents that work from screenshots, such as Claude computer use."""

    BOTH = "both"


class HoneypotVariantSpec(BaseModel):
    """Shared base fields every variant spec must define."""

    variant_id: str = Field(..., description="Short stable identifier, e.g. 'semantic-trap-v1'.")
    name: str
    description: str
    concealment_strategy: ConcealmentStrategy
    target_failure_modes: list[FailureMode] = Field(..., min_length=1)
    target_modality: TargetModality
    fidelity_level: FidelityLevel
    honeytoken_type: HoneytokenType
    acceptance_criterion: str = Field(
        ..., description="What would make an agent judge this page/path worth pursuing."
    )
    notes: str = ""

    @field_validator("target_failure_modes")
    @classmethod
    def must_cover_at_least_one_mode(cls, v: list[FailureMode]) -> list[FailureMode]:
        if not v:
            raise ValueError("A honeypot variant must target at least one FailureMode.")
        return v


class SemanticTrapSpec(HoneypotVariantSpec):
    """Spec for a semantically enriched trap page."""

    content_topic: str = Field(
        ..., description="e.g. 'quarterly financial export', 'customer database export'."
    )
    content_generation_strategy: str = Field(
        ..., description="e.g. 'faker_synthetic', 'llm_assisted', 'hybrid'."
    )


class PromptInjectionTrapSpec(HoneypotVariantSpec):
    """Spec for a prompt-injection trap."""

    injection_surface: str = Field(
        ..., description="Where the instruction lives, e.g. 'html_comment', 'aria_label', 'json_ld'."
    )
    injected_instruction_template: str = Field(
        ..., description="Instruction text; must contain a '{canary_token}' placeholder."
    )
    expected_side_effect: str = Field(
        ..., description="Detectable, passive behavioural marker, e.g. 'canary_in_output'."
    )

    @field_validator("injected_instruction_template")
    @classmethod
    def must_contain_canary_placeholder(cls, v: str) -> str:
        if "{canary_token}" not in v:
            raise ValueError("injected_instruction_template must contain a '{canary_token}' placeholder.")
        return v


class DynamicLinkGraphTrapSpec(HoneypotVariantSpec):
    """Spec for a dynamic link-graph trap."""

    max_depth: int = Field(..., gt=0)
    teaser_template: str = Field(
        ..., description="Must contain '{page_number}' and '{max_depth}' placeholders."
    )
    termination_condition: str = Field(
        ..., description="e.g. 'max_depth_reached', 'timeout_idle_seconds'."
    )
    idle_timeout_seconds: int | None = Field(
        default=None, description="Required if termination_condition uses an idle timeout."
    )

    @field_validator("teaser_template")
    @classmethod
    def must_contain_page_placeholders(cls, v: str) -> str:
        if "{page_number}" not in v or "{max_depth}" not in v:
            raise ValueError(
                "teaser_template must contain '{page_number}' and '{max_depth}' placeholders."
            )
        return v