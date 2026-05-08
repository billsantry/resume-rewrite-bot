"""
MatchMeter scorer service.

Scores how well a single JobListing matches a CandidateProfile. Returns
a 1-10 score, a one-sentence match_reason, and a list of gaps.

The scoring rubric and output contract live in `prompts/matchmeter_v2.md`.
The output schema lives in `cert/schemas.py`. This module wires them
together via `cert.llm`.

Provider: OpenAI (gpt-4o-mini). Inherited from v1.5 of the rewriter for
cost reasons; quality is sufficient for 1-10 scoring with calibrated
prompts. Reconsider if score calibration drifts on real user data.
"""

from __future__ import annotations

from cert.llm import load_prompt, structured_output
from cert.schemas import CandidateProfile, JobListing, MatchScore


_SYSTEM_PROMPT = load_prompt("matchmeter_v2")


def score_match(profile: CandidateProfile, listing: JobListing) -> MatchScore:
    """Score how well a candidate fits a single job listing.

    Args:
        profile: The candidate's CandidateProfile from `parse_resume`.
        listing: A normalized JobListing from `search_usajobs`.

    Returns:
        A MatchScore with score (1-10), match_reason (≤140 chars), and
        a list of gaps.

    Raises:
        ValueError: If the LLM returns invalid JSON.
        pydantic.ValidationError: If the response fails schema validation.
    """
    user_message = _format_user_message(profile, listing)
    return structured_output(
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
        schema=MatchScore,
        provider="openai",
    )


def _format_user_message(profile: CandidateProfile, listing: JobListing) -> str:
    """Build the user-turn content per the matchmeter_v2 prompt template."""
    return (
        "Score this federal job listing against the candidate's profile.\n\n"
        "<candidate_profile>\n"
        f"{profile.model_dump_json(indent=2)}\n"
        "</candidate_profile>\n\n"
        "<job_listing>\n"
        f"Title: {listing.title}\n"
        f"Agency: {listing.agency}\n"
        f"Grade: {listing.grade}\n"
        "Qualifications:\n"
        f"{listing.qualifications_text}\n"
        "</job_listing>"
    )