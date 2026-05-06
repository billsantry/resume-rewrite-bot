"""
Tool registry for Cert.

Each capability the agent can invoke is declared here as a ToolDefinition.
Today the Flask handler in app.py calls these tools imperatively; the
registry is essentially documentation that the orchestration logic lines
up with the published prompts.

Tomorrow, when we migrate to an agentic API (Anthropic tool use, OpenAI
Responses, etc.), the same definitions become the tools array on the API
call. The descriptions you see here are the same strings the LLM will
read when deciding what to invoke.

Three tools, in the order the agent uses them:

    1. parse_resume      — runs once at session start
    2. search_usajobs    — runs 1-3 times per session
    3. score_match       — runs once per listing for the top 25

Handler functions are deliberately set to None for now. They get wired
up in cert/services/* when those modules are implemented. Setting
handler=None and importing this registry from app.py is safe: app.py
will call the service functions directly until the agentic migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

from cert.schemas import (
    CandidateProfile,
    JobListing,
    MatchScore,
    SearchParams,
)


# ---------------------------------------------------------------------------
# Tool definition shape
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    """A single tool the agent can invoke.

    Maps cleanly onto the tools array shape used by Anthropic tool use and
    OpenAI Responses API function calls. The handler field is what makes
    this executable from Python; agentic callers will ignore it and dispatch
    by name.
    """

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    handler: Callable | None = None


# ---------------------------------------------------------------------------
# Per-tool input wrappers
# ---------------------------------------------------------------------------
# Some schemas in cert.schemas are outputs of one tool and inputs to another
# (e.g. CandidateProfile is the output of parse_resume and an input to
# score_match). The wrapper classes here disambiguate.


class ParseResumeInput(BaseModel):
    resume_text: str


class ScoreMatchInput(BaseModel):
    profile: CandidateProfile
    listing: JobListing


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


parse_resume_tool = ToolDefinition(
    name="parse_resume",
    description=(
        "Parse a candidate's resume into a structured CandidateProfile. "
        "Returns federal employment status, current grade and agency, "
        "veteran preference indicators, inferred occupational series, and "
        "search keywords. Call this exactly once at the start of a "
        "session, before any search or scoring tool. The resulting "
        "profile is the source of truth for all eligibility decisions "
        "downstream; do not re-parse the resume mid-session."
    ),
    input_schema=ParseResumeInput,
    output_schema=CandidateProfile,
    handler=None,  # cert.services.parser.parse_resume
)


search_usajobs_tool = ToolDefinition(
    name="search_usajobs",
    description=(
        "Query the USAJobs API for current federal job postings. Returns "
        "a list of normalized JobListing objects. Call after parsing the "
        "resume with parameters derived from the candidate's profile and "
        "any user-stated preferences. If the first call returns fewer "
        "than 5 results, broaden once: drop the most restrictive keyword "
        "and widen the grade range by one level. Do not exceed 3 search "
        "calls per session."
    ),
    input_schema=SearchParams,
    output_schema=JobListing,  # In practice returns list[JobListing]
    handler=None,  # cert.services.search.search_usajobs
)


score_match_tool = ToolDefinition(
    name="score_match",
    description=(
        "Score how well a single JobListing matches a CandidateProfile. "
        "Returns an integer score from 1 to 10, a one-sentence "
        "match_reason that cites specific resume content (not generic "
        "praise), and a short list of gaps the candidate may be missing. "
        "Call once per listing for the top 25 listings returned by "
        "search_usajobs. Never invent qualifications or experience the "
        "resume does not contain."
    ),
    input_schema=ScoreMatchInput,
    output_schema=MatchScore,
    handler=None,  # cert.services.scorer.score_match
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


TOOL_REGISTRY: list[ToolDefinition] = [
    parse_resume_tool,
    search_usajobs_tool,
    score_match_tool,
]


def get_tool(name: str) -> ToolDefinition:
    """Look up a tool by name. Raises KeyError if not found."""
    for tool in TOOL_REGISTRY:
        if tool.name == name:
            return tool
    raise KeyError(f"Tool not registered: {name}")
