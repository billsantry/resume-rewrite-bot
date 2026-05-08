"""
Resume parser service.

Converts pasted resume text into a structured CandidateProfile.

The parsing rules and output contract live in `prompts/resume_parser.md`.
The output schema lives in `cert/schemas.py`. This module is just the
small bit of glue that wires them together via `cert.llm`.

Provider: Anthropic (Claude Sonnet 4.6). Structured-output fidelity on
typed schemas is the deciding factor; revisit if a cheaper model passes
the same parse-quality bar.
"""

from __future__ import annotations

from cert.llm import load_prompt, structured_output
from cert.schemas import CandidateProfile


# Loaded once at import time. If the prompt file is missing, fail loudly
# at startup rather than on the first user request.
_SYSTEM_PROMPT = load_prompt("resume_parser")


def parse_resume(resume_text: str) -> CandidateProfile:
    """Parse a resume into a structured CandidateProfile.

    Args:
        resume_text: Raw text pasted from the user. The parser is
            tolerant of formatting variation; do not pre-process.

    Returns:
        A CandidateProfile validated against the schema.

    Raises:
        ValueError: If the resume text is empty or the LLM returns
            invalid JSON.
        pydantic.ValidationError: If the response fails schema validation.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError("resume_text is empty")

    return structured_output(
        system_prompt=_SYSTEM_PROMPT,
        user_message=f"<resume>\n{resume_text}\n</resume>",
        schema=CandidateProfile,
        provider="anthropic",
    )