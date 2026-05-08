"""
Cert smoke test.

Exercises the full pipeline end-to-end: resume parsing, USAJobs search,
and scoring. Useful for verifying that all services and the LLM
abstraction work together before they get wired into Flask routes.

Usage (from the project root, with venv activated):
    python scripts/smoke_test.py

Requires the following environment variables in .env:
    ANTHROPIC_API_KEY
    OPENAI_API_KEY
    USAJOBS_API_KEY
    USAJOBS_USER_EMAIL
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cert.schemas import SearchParams
from cert.services.parser import parse_resume
from cert.services.scorer import score_match
from cert.services.search import search_usajobs


SAMPLE_RESUME = """
Jane Doe
Washington, DC | jane@example.com

PROFESSIONAL EXPERIENCE

U.S. Department of State, Washington, DC
Information Technology Specialist (GS-14), 2022 - Present
- Led enterprise AI evaluation across the bureau, drafting policy guidance
  and architecture standards for Azure OpenAI deployments.
- Reduced cloud spend by 35% via FedRAMP-compliant cost-optimization
  practices and reserved capacity planning.
- Coordinated with OMB and OPM on emerging-technology compliance reviews.

U.S. Department of State, Washington, DC
Information Technology Specialist (GS-13), 2019 - 2022
- Engineered identity-management infrastructure supporting 50,000 users
  across 270 missions worldwide.
- Co-authored department-wide cybersecurity guidance aligned with
  NIST 800-53.

EDUCATION
M.S. Information Systems, Johns Hopkins University, 2018
B.A. Political Science, University of Virginia, 2014

CLEARANCE
TS/SCI with poly (active)
"""


def banner(text: str) -> None:
    print()
    print("=" * 60)
    print(text)
    print("=" * 60)


def main() -> int:
    banner("Step 1: parse_resume")
    profile = parse_resume(SAMPLE_RESUME)
    print(profile.model_dump_json(indent=2))

    banner("Step 2: search_usajobs")
    keyword = "cybersecurity"
    print(f"Using keyword: {keyword!r}")
    params = SearchParams(
        keyword=keyword,
        pay_grade_low=profile.grade_floor.replace("GS-", ""),
        pay_grade_high=profile.grade_ceiling.replace("GS-", ""),
        who_may_apply="public",
        results_per_page=5,
    )
    listings = search_usajobs(params)
    print(f"Found {len(listings)} listings")

    if not listings:
        print("No listings returned. Smoke test cannot fully complete.")
        print("Try a different keyword in scripts/smoke_test.py, or "
              "broaden grade range.")
        return 1

    first = listings[0]
    print(f"\nFirst listing:")
    print(f"  Title:    {first.title}")
    print(f"  Agency:   {first.agency}")
    print(f"  Location: {first.location}")
    print(f"  Grade:    {first.grade}")
    print(f"  Closing:  {first.closing_date}")

    banner("Step 3: score_match")
    score = score_match(profile, first)
    print(score.model_dump_json(indent=2))

    banner("Pipeline healthy. All three services worked end to end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())