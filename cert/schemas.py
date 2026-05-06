"""
Pydantic schemas for Cert.

These are the typed data shapes that cross every boundary in the system:
between the parser and the agent loop, between the search call and the
scorer, between the backend and the frontend, and (later) between the
agent LLM and its tools.

Keep these strict and minimal. Anything that doesn't belong on the wire
doesn't belong here. PII, internal flags, and convenience fields go in
service-layer classes, not in these schemas.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ParseConfidence(str, Enum):
    """How confident the parser is in the resulting CandidateProfile."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EligibilityTag(str, Enum):
    """Why this listing is being shown to this candidate.

    Computed deterministically from the candidate profile and the
    listing's hiring paths. Never inferred by an LLM.
    """

    OPEN_TO_PUBLIC = "open_to_public"
    STATUS_QUALIFIED = "status_qualified"
    VETERANS_QUALIFIED = "veterans_qualified"
    INELIGIBLE = "ineligible"  # filtered out, never shown


# ---------------------------------------------------------------------------
# CandidateProfile: output of the resume parser
# ---------------------------------------------------------------------------


class CandidateProfile(BaseModel):
    """Structured profile derived from a pasted resume.

    The single source of truth for eligibility decisions in the agent loop.
    Field semantics are defined in prompts/resume_parser.md; keep these in
    sync if you change either one.
    """

    current_federal_employee: bool
    current_grade: str | None = None
    current_series: str | None = None
    current_agency: str | None = None
    time_in_current_grade_weeks: int | None = None
    veteran_preference_likely: bool

    grade_floor: str = Field(
        description="Lowest GS grade worth showing this candidate, e.g. 'GS-13'."
    )
    grade_ceiling: str = Field(
        description="Highest GS grade this candidate could plausibly qualify for."
    )

    inferred_series: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Up to four OPM occupational series codes ranked by fit.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Distinctive resume terms used as USAJobs search keywords.",
    )

    parse_confidence: ParseConfidence
    ambiguities: list[str] = Field(
        default_factory=list,
        description="Human-readable notes on anything the parser had to guess at.",
    )


# ---------------------------------------------------------------------------
# SearchParams: input to the USAJobs search tool
# ---------------------------------------------------------------------------


class SearchParams(BaseModel):
    """Parameters for a single USAJobs API query.

    Field names are camelCase'd to USAJobs' query parameter names at the
    HTTP boundary in cert.services.search; keep this layer pythonic.
    """

    keyword: str = Field(
        description="Free-text keyword. Drives the bulk of result relevance."
    )
    pay_grade_low: str | None = Field(
        default=None,
        description="Numeric grade floor as USAJobs expects it, e.g. '13' for GS-13.",
    )
    pay_grade_high: str | None = Field(
        default=None,
        description="Numeric grade ceiling as USAJobs expects it.",
    )
    job_category_codes: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="OPM occupational series codes to filter on.",
    )
    who_may_apply: Literal["public", "all"] = Field(
        default="public",
        description="'public' for public listings, 'all' to include status-only.",
    )
    results_per_page: int = Field(default=25, ge=1, le=500)


# ---------------------------------------------------------------------------
# JobListing: normalized USAJobs response, pre-scoring
# ---------------------------------------------------------------------------


class JobListing(BaseModel):
    """One USAJobs posting after light normalization.

    Constructed in cert.services.search from a raw USAJobs response item.
    Holds only what the rest of the pipeline needs; the raw response is
    discarded.
    """

    control_number: str
    title: str
    agency: str
    location: str
    grade: str  # e.g., "GS-13", "GS-12 to GS-13", "SES"
    salary_min: int | None = None
    salary_max: int | None = None
    closing_date: str | None = None  # ISO date string, kept as string for simplicity
    apply_url: str
    hiring_paths: list[str] = Field(
        default_factory=list,
        description="USAJobs HiringPath codes such as 'public', 'fed-internal', 'vet'.",
    )
    qualifications_text: str = Field(
        default="",
        description="Combined PositionTitle + QualificationSummary + MajorDuties.",
    )


# ---------------------------------------------------------------------------
# MatchScore: output of the per-listing scorer
# ---------------------------------------------------------------------------


class MatchScore(BaseModel):
    """Score for a single (CandidateProfile, JobListing) pair."""

    score: int = Field(ge=1, le=10)
    match_reason: str = Field(
        max_length=140,
        description=(
            "One sentence. Must cite specific resume content, not generic praise."
        ),
    )
    gaps: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Qualifications the candidate may be missing.",
    )


# ---------------------------------------------------------------------------
# JobResult: final UI-bound shape returned to the frontend
# ---------------------------------------------------------------------------


class JobResult(BaseModel):
    """What the frontend renders as a result card.

    Composed in the Flask handler from a JobListing, a MatchScore, and the
    eligibility evaluation. This is the only schema the JSON response
    serializes; nothing internal leaks.
    """

    control_number: str
    title: str
    agency: str
    location: str
    grade: str
    salary_range: str  # human-readable, e.g. "$103,409 - $134,435"
    closing_date: str  # ISO date string
    apply_url: str
    match_score: int = Field(ge=1, le=10)
    match_reason: str = Field(max_length=140)
    gaps: list[str] = Field(default_factory=list)
    eligibility_tag: EligibilityTag
    eligibility_note: str = Field(max_length=80)
