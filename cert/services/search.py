"""
USAJobs search service.

Single-purpose module: convert SearchParams into a list of normalized
JobListing objects pulled from data.usajobs.gov. Handles authentication,
one rate-limit retry per the SRS, and the somewhat verbose USAJobs
response schema.

Authentication credentials are read from environment variables. The
USAJobs API requires both a key and the email address that was used to
register that key (sent as User-Agent).
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from cert.schemas import JobListing, SearchParams


USAJOBS_SEARCH_URL = "https://data.usajobs.gov/api/search"
RATE_LIMIT_RETRY_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 20.0


def search_usajobs(params: SearchParams) -> list[JobListing]:
    """Query USAJobs and return a list of normalized JobListing objects.

    Args:
        params: SearchParams describing the query. See `cert.schemas`.

    Returns:
        A list of JobListing objects. May be empty if no results match.
        Listings missing required fields (title, apply URL) are dropped
        rather than raising; we prefer a shorter list to a crash.

    Raises:
        RuntimeError: If credentials are missing or the API rejects them.
        httpx.HTTPError: For network-level failures.
    """
    api_key = os.getenv("USAJOBS_API_KEY")
    user_email = os.getenv("USAJOBS_USER_EMAIL")
    if not api_key or not user_email:
        raise RuntimeError(
            "USAJOBS_API_KEY and USAJOBS_USER_EMAIL must both be set in .env"
        )

    query = _build_query_params(params)
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": user_email,
        "Authorization-Key": api_key,
    }

    payload = _request_with_retry(query, headers)
    return _normalize_response(payload)


# ---------------------------------------------------------------------------
# Request construction and execution
# ---------------------------------------------------------------------------


def _build_query_params(params: SearchParams) -> dict[str, str]:
    """Translate SearchParams into the camelCase params USAJobs expects."""
    query: dict[str, str] = {
        "Keyword": params.keyword,
        "WhoMayApply": params.who_may_apply,
        "ResultsPerPage": str(params.results_per_page),
    }
    if params.pay_grade_low:
        query["PayGradeLow"] = params.pay_grade_low
    if params.pay_grade_high:
        query["PayGradeHigh"] = params.pay_grade_high
    if params.job_category_codes:
        # USAJobs accepts semicolon-separated category codes
        query["JobCategoryCode"] = ";".join(params.job_category_codes)
    return query


def _request_with_retry(
    query: dict[str, str], headers: dict[str, str]
) -> dict[str, Any]:
    """GET the search endpoint, with one retry on HTTP 429."""
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(USAJOBS_SEARCH_URL, params=query, headers=headers)
        if response.status_code == 429:
            time.sleep(RATE_LIMIT_RETRY_SECONDS)
            response = client.get(
                USAJOBS_SEARCH_URL, params=query, headers=headers
            )

        if response.status_code in (401, 403):
            raise RuntimeError(
                f"USAJobs auth failed (HTTP {response.status_code}). "
                "Check USAJOBS_API_KEY and USAJOBS_USER_EMAIL in .env."
            )

        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Response normalization
# ---------------------------------------------------------------------------


def _normalize_response(payload: dict[str, Any]) -> list[JobListing]:
    """Extract listings from the USAJobs response and normalize each."""
    items = payload.get("SearchResult", {}).get("SearchResultItems", [])
    listings: list[JobListing] = []
    for item in items:
        normalized = _normalize_item(item)
        if normalized is not None:
            listings.append(normalized)
    return listings


def _normalize_item(item: dict[str, Any]) -> JobListing | None:
    """Convert one SearchResultItem into a JobListing.

    Returns None if the item is missing fields we need to render a
    result card. Dropping a malformed listing is preferable to crashing
    the whole search.
    """
    descriptor = item.get("MatchedObjectDescriptor")
    if not descriptor:
        return None

    user_area = descriptor.get("UserArea", {}).get("Details", {})

    title = descriptor.get("PositionTitle", "").strip()
    apply_url = _extract_apply_url(descriptor)
    if not title or not apply_url:
        return None

    return JobListing(
        control_number=descriptor.get("PositionID", ""),
        title=title,
        agency=_extract_agency(descriptor),
        location=descriptor.get("PositionLocationDisplay", ""),
        grade=_build_grade_string(descriptor, user_area),
        salary_min=_extract_salary(descriptor, "MinimumRange"),
        salary_max=_extract_salary(descriptor, "MaximumRange"),
        closing_date=_extract_closing_date(descriptor),
        apply_url=apply_url,
        hiring_paths=_extract_hiring_paths(user_area),
        qualifications_text=_build_qualifications_text(descriptor, user_area),
    )


def _extract_apply_url(descriptor: dict[str, Any]) -> str:
    """Return the canonical apply URL, falling back to the position page."""
    apply_uris = descriptor.get("ApplyURI", [])
    if isinstance(apply_uris, list) and apply_uris:
        return apply_uris[0]
    return descriptor.get("PositionURI", "")


def _extract_agency(descriptor: dict[str, Any]) -> str:
    """Prefer OrganizationName, fall back to DepartmentName."""
    return (
        descriptor.get("OrganizationName")
        or descriptor.get("DepartmentName")
        or ""
    )


def _build_grade_string(
    descriptor: dict[str, Any], user_area: dict[str, Any]
) -> str:
    """Build a human-readable grade like 'GS-13/14' from USAJobs fields."""
    pay_plan = ""
    job_grade = descriptor.get("JobGrade", [])
    if isinstance(job_grade, list) and job_grade:
        pay_plan = job_grade[0].get("Code", "")

    low = user_area.get("LowGrade", "")
    high = user_area.get("HighGrade", "")

    if low and high and low != high:
        return f"{pay_plan}-{low}/{high}".strip("-")
    if low:
        return f"{pay_plan}-{low}".strip("-")
    return pay_plan or "Unknown"


def _extract_salary(descriptor: dict[str, Any], key: str) -> int | None:
    """Pull MinimumRange or MaximumRange from PositionRemuneration as int."""
    remuneration = descriptor.get("PositionRemuneration", [])
    if not isinstance(remuneration, list) or not remuneration:
        return None
    raw = remuneration[0].get(key)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return None


def _extract_closing_date(descriptor: dict[str, Any]) -> str | None:
    """Return the date portion of ApplicationCloseDate as YYYY-MM-DD."""
    raw = descriptor.get("ApplicationCloseDate", "")
    return raw[:10] if raw else None


def _extract_hiring_paths(user_area: dict[str, Any]) -> list[str]:
    """Return HiringPath as a list of strings, defaulting to empty."""
    paths = user_area.get("HiringPath", [])
    return paths if isinstance(paths, list) else []


def _build_qualifications_text(
    descriptor: dict[str, Any], user_area: dict[str, Any]
) -> str:
    """Combine PositionTitle, QualificationSummary, and MajorDuties."""
    title = descriptor.get("PositionTitle", "")
    summary = descriptor.get("QualificationSummary", "")

    duties_raw = user_area.get("MajorDuties", [])
    if isinstance(duties_raw, list):
        duties = "\n".join(str(d) for d in duties_raw)
    else:
        duties = str(duties_raw or "")

    parts = [s for s in (title, summary, duties) if s]
    return "\n\n".join(parts)