"""
Cert agent orchestrator.

Today: this module implements the rules in prompts/agent_system.md
imperatively in Python. The Flask handler in app.py calls run_session()
once per user request and returns its result as JSON.

Tomorrow: this module becomes a thin wrapper around an LLM tool-use
loop. The agent_system prompt becomes the system message; the three
services become tools the model dispatches by name. Both
implementations should produce the same SessionResult, so the
migration is invisible to the Flask layer and the frontend.
"""

from __future__ import annotations

import re

from cert.schemas import (
    CandidateProfile,
    EligibilityTag,
    JobListing,
    JobResult,
    MatchScore,
    SearchParams,
    SessionResult,
    SessionState,
)
from cert.services.parser import parse_resume
from cert.services.scorer import score_match
from cert.services.search import search_usajobs


# Per the decision rules in prompts/agent_system.md
MAX_LISTINGS_TO_SCORE = 25
DEFAULT_RESULTS_TO_RETURN = 7
HARD_MAX_RESULTS = 10
MIN_RESULTS_BEFORE_BROADENING = 5
WEAK_SCORE_THRESHOLD = 5  # if all surviving scores below this, return only one


def run_session(
    resume_text: str,
    user_prompt: str | None = None,
) -> SessionResult:
    """Run a complete Cert session: parse, search, score, return results."""
    # Step 1: parse the resume
    profile = parse_resume(resume_text)

    # Step 2: surface disambiguation if the parser was unsure about
    # federal status (the only ambiguity worth blocking on for MVP)
    if _needs_disambiguation(profile):
        return SessionResult(
            session_state=SessionState(
                profile_summary=_render_profile_summary(profile),
                queries_run=0,
                listings_evaluated=0,
                needs_disambiguation=True,
                disambiguation_question=(
                    "I'm not sure whether to search as a current federal "
                    "employee or as a member of the public. Which "
                    "describes you?"
                ),
            ),
            results=[],
        )

    # Step 3: build initial search queries
    queries = _build_initial_queries(profile, user_prompt)

    # Step 4: execute searches and deduplicate by control_number
    listings = _execute_searches(queries)

    # Step 5: broaden once if too few results
    if len(listings) < MIN_RESULTS_BEFORE_BROADENING and queries:
        broader = _build_broaden_query(queries[0])
        broader_listings = search_usajobs(broader)
        listings = _dedup(listings + broader_listings)
        queries.append(broader)

    # Step 6: filter by eligibility (deterministic, not LLM judgment)
    eligible: list[tuple[JobListing, EligibilityTag, str]] = []
    for listing in listings[:MAX_LISTINGS_TO_SCORE]:
        tag, note = _evaluate_eligibility(profile, listing)
        if tag == EligibilityTag.INELIGIBLE:
            continue
        if not _grade_fits(profile, listing):
            continue
        eligible.append((listing, tag, note))

    # Step 7: score the eligible listings
    scored: list[tuple[JobListing, EligibilityTag, str, MatchScore]] = []
    for listing, tag, note in eligible:
        score = score_match(profile, listing)
        scored.append((listing, tag, note, score))

    # Step 8: rank and trim. If all matches are weak, return only the
    # single best with honest framing rather than padding the list.
    scored.sort(key=lambda row: row[3].score, reverse=True)
    if scored and scored[0][3].score < WEAK_SCORE_THRESHOLD:
        scored = scored[:1]
    else:
        scored = scored[:DEFAULT_RESULTS_TO_RETURN]

    # Step 9: assemble the final JobResult list
    results = [
        JobResult(
            control_number=listing.control_number,
            title=listing.title,
            agency=listing.agency,
            location=listing.location,
            grade=listing.grade,
            salary_range=_format_salary_range(listing),
            closing_date=listing.closing_date or "",
            apply_url=listing.apply_url,
            match_score=score.score,
            match_reason=score.match_reason,
            gaps=score.gaps,
            eligibility_tag=tag,
            eligibility_note=note,
        )
        for listing, tag, note, score in scored
    ]

    return SessionResult(
        session_state=SessionState(
            profile_summary=_render_profile_summary(profile),
            queries_run=len(queries),
            listings_evaluated=len(eligible),
            needs_disambiguation=False,
            disambiguation_question=None,
        ),
        results=results,
    )


# ---------------------------------------------------------------------------
# Disambiguation
# ---------------------------------------------------------------------------


def _needs_disambiguation(profile: CandidateProfile) -> bool:
    """Whether to ask the user to clarify before searching.

    Only block on disambiguation when the parser is genuinely unsure
    whether the candidate is currently a federal employee. Other
    ambiguities (date precision, series inference, veteran preference)
    do not warrant interrupting the user; they are handled downstream
    by tags, scorer caveats, or the [Edit] affordance.
    """
    if profile.parse_confidence == "high":
        return False

    # If the parser determined the candidate IS a current fed, trust
    # that even at medium/low confidence; the rest of the pipeline
    # works correctly with that assumption.
    if profile.current_federal_employee:
        return False

    # Only at low confidence on a non-federal classification do we
    # ask. Medium confidence on non-federal is good enough to search.
    if profile.parse_confidence != "low":
        return False

    # And only if an ambiguity actually concerns federal status.
    uncertainty_words = ("uncertain", "unclear", "cannot determine", "ambiguous")
    federal_words = ("federal", "fed", "status", "employee", "employer")

    for ambiguity in profile.ambiguities:
        lower = ambiguity.lower()
        if any(u in lower for u in uncertainty_words) and any(
            f in lower for f in federal_words
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Search query construction
# ---------------------------------------------------------------------------


def _build_initial_queries(
    profile: CandidateProfile,
    user_prompt: str | None,
) -> list[SearchParams]:
    """Build initial search queries from the profile and any user prompt."""
    keyword = _select_keyword(profile, user_prompt)
    who_may_apply = "all" if profile.current_federal_employee else "public"

    return [
        SearchParams(
            keyword=keyword,
            pay_grade_low=_grade_to_number(profile.grade_floor),
            pay_grade_high=_grade_to_number(profile.grade_ceiling),
            job_category_codes=profile.inferred_series[:3],
            who_may_apply=who_may_apply,
            results_per_page=25,
        )
    ]


def _select_keyword(
    profile: CandidateProfile,
    user_prompt: str | None,
) -> str:
    """Choose the most likely-to-succeed keyword.

    Priority:
    1. User-supplied prompt (most direct expression of intent).
    2. First single-word keyword from the profile (broadest match).
    3. First keyword from the profile (still better than nothing).
    4. Empty string (USAJobs accepts this; grade/category still filter).
    """
    if user_prompt and user_prompt.strip():
        return user_prompt.strip()

    single_word = [k for k in profile.keywords if " " not in k]
    if single_word:
        return single_word[0]

    if profile.keywords:
        return profile.keywords[0]

    return ""


def _build_broaden_query(original: SearchParams) -> SearchParams:
    """Construct a broader version of the original query.

    Per agent_system.md: drop the most restrictive filter (job category)
    and widen the grade range by one on each side.
    """
    return SearchParams(
        keyword=original.keyword,
        pay_grade_low=_widen_grade_down(original.pay_grade_low),
        pay_grade_high=_widen_grade_up(original.pay_grade_high),
        job_category_codes=[],
        who_may_apply=original.who_may_apply,
        results_per_page=25,
    )


# ---------------------------------------------------------------------------
# Search execution and deduplication
# ---------------------------------------------------------------------------


def _execute_searches(queries: list[SearchParams]) -> list[JobListing]:
    """Run all queries and return deduplicated listings."""
    all_listings: list[JobListing] = []
    for query in queries:
        all_listings.extend(search_usajobs(query))
    return _dedup(all_listings)


def _dedup(listings: list[JobListing]) -> list[JobListing]:
    """Remove duplicate listings by control_number, preserving order."""
    seen: set[str] = set()
    unique: list[JobListing] = []
    for listing in listings:
        if listing.control_number and listing.control_number not in seen:
            seen.add(listing.control_number)
            unique.append(listing)
    return unique


# ---------------------------------------------------------------------------
# Eligibility (deterministic, not LLM judgment)
# ---------------------------------------------------------------------------


def _evaluate_eligibility(
    profile: CandidateProfile,
    listing: JobListing,
) -> tuple[EligibilityTag, str]:
    """Compute eligibility tag and human-readable note for a listing."""
    paths = set(listing.hiring_paths)

    if "public" in paths:
        return EligibilityTag.OPEN_TO_PUBLIC, "Open to U.S. citizens"

    fed_paths = {"fed-internal", "fed-competitive", "fed-excepted"}
    if profile.current_federal_employee and (paths & fed_paths):
        return EligibilityTag.STATUS_QUALIFIED, "You qualify under federal status"

    if profile.veteran_preference_likely and "vet" in paths:
        return EligibilityTag.VETERANS_QUALIFIED, "You qualify via veteran preference"

    return EligibilityTag.INELIGIBLE, ""


def _grade_fits(profile: CandidateProfile, listing: JobListing) -> bool:
    """Check whether the listing's grade is in a sensible range.

    Returns True for non-GS listings (DL, SES, NH, etc.) - the scorer
    will flag any real mismatch in match_reason. We only filter when
    we have a clean GS-to-GS comparison.
    """
    listing_grade = _extract_gs_number(listing.grade)
    if listing_grade is None:
        return True

    floor = _extract_gs_number(profile.grade_floor)
    ceiling = _extract_gs_number(profile.grade_ceiling)

    if floor is not None and listing_grade < floor - 2:
        return False
    if ceiling is not None and listing_grade > ceiling:
        return False

    return True


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_profile_summary(profile: CandidateProfile) -> str:
    """One human-readable sentence describing the search context."""
    parts = ["Searching as"]

    if profile.current_federal_employee:
        if profile.current_grade:
            parts.append(f"a current {profile.current_grade}")
        else:
            parts.append("a current federal employee")
        if profile.current_agency:
            parts.append(f"at {profile.current_agency}")
    else:
        parts.append("a member of the public")

    if profile.veteran_preference_likely:
        parts.append("with veteran preference")

    return " ".join(parts) + "."


def _format_salary_range(listing: JobListing) -> str:
    """Format a salary range for display, with sensible fallbacks."""
    if listing.salary_min and listing.salary_max:
        return f"${listing.salary_min:,} - ${listing.salary_max:,}"
    if listing.salary_min:
        return f"${listing.salary_min:,}+"
    return "Not specified"


# ---------------------------------------------------------------------------
# Grade parsing
# ---------------------------------------------------------------------------


_GS_GRADE_RE = re.compile(r"GS[-\s]?(\d+)", re.IGNORECASE)


def _extract_gs_number(grade_str: str) -> int | None:
    """Extract the numeric portion of a GS grade like 'GS-14' -> 14."""
    if not grade_str:
        return None
    match = _GS_GRADE_RE.search(grade_str)
    return int(match.group(1)) if match else None


def _grade_to_number(grade_str: str) -> str | None:
    """Convert 'GS-13' to '13' for USAJobs API parameters."""
    n = _extract_gs_number(grade_str)
    return str(n) if n is not None else None


def _widen_grade_down(grade_num: str | None) -> str | None:
    """Widen a grade-low parameter by one (e.g. '13' -> '12')."""
    if grade_num is None:
        return None
    try:
        return str(max(1, int(grade_num) - 1))
    except ValueError:
        return grade_num


def _widen_grade_up(grade_num: str | None) -> str | None:
    """Widen a grade-high parameter by one, capped at 15."""
    if grade_num is None:
        return None
    try:
        return str(min(15, int(grade_num) + 1))
    except ValueError:
        return grade_num