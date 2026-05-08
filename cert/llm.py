"""
LLM abstraction for Cert.

One module, two providers (Anthropic, OpenAI), one job: send a prompt
and get back a Pydantic-validated structured response.

This is the only place in the codebase that imports the Anthropic or
OpenAI SDK. Every other module calls `structured_output()`. When we
migrate to OpenAI's Responses API, switch model providers, or add
streaming, only this file changes.

Public API:
    load_prompt(name)         -> str
    structured_output(...)    -> BaseModel subclass instance

Conventions:
    * Caller passes provider explicitly (no implicit dispatch on
      schema or model name). Defaults are sensible but every call
      site reads with intent.
    * Caller passes the system prompt as a string, typically the
      output of load_prompt(). Prompts are not loaded by name inside
      this module to keep service code grep-able.
    * Temperature defaults to 0.0 because every current use is
      structured output where determinism matters more than variety.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal, TypeVar

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel


# Load .env once at import time. Idempotent and does not override
# variables already present in the environment, so this is safe to do
# even if app.py also calls load_dotenv() at startup.
load_dotenv()


T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Default models
# ---------------------------------------------------------------------------
# Update here when newer or cheaper models become available. Do not
# change at the call site unless intentionally diverging from the default.

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Lazy client singletons
# ---------------------------------------------------------------------------
# Clients are instantiated on first use rather than at import time. This
# means an environment with only one of the two API keys can still
# import this module; the missing-key error surfaces only when something
# actually tries to use that provider.

_anthropic_client: Anthropic | None = None
_openai_client: OpenAI | None = None


def _get_anthropic_client() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to .env in the project "
                "root or export it before running Cert."
            )
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Add it to .env in the project "
                "root or export it before running Cert."
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Matches the first triple-backtick code block under a "## System prompt"
# heading. We use this rather than sending the entire .md file because
# each prompt file also contains documentation, test cases, and notes
# that are for humans, not the model.
_SYSTEM_PROMPT_PATTERN = re.compile(
    r"## System prompt\s*\n+```\s*\n(.*?)\n```",
    re.DOTALL,
)


def load_prompt(name: str) -> str:
    """Load a prompt by name from prompts/<name>.md.

    Returns only the contents of the system prompt code block. Other
    sections of the file (intro, test cases, future-work notes) are
    stripped because they are addressed to human readers, not the LLM.

    Raises:
        FileNotFoundError: If prompts/<name>.md does not exist.
        ValueError: If the file has no parseable system prompt block.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    text = path.read_text()
    match = _SYSTEM_PROMPT_PATTERN.search(text)
    if not match:
        raise ValueError(
            f"No '## System prompt' code block found in {path}. Each prompt "
            "file must contain a triple-backtick code block under that "
            "heading."
        )
    return match.group(1).strip()


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


def structured_output(
    *,
    system_prompt: str,
    user_message: str,
    schema: type[T],
    provider: Literal["anthropic", "openai"] = "anthropic",
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> T:
    """Call an LLM and return a Pydantic-validated response.

    Args:
        system_prompt: The system message. Typically the output of
            `load_prompt(name)`.
        user_message: The user-turn content. The data the LLM should
            process (resume text, listing data, etc.).
        schema: A Pydantic BaseModel subclass. The response is parsed
            as JSON and validated against this schema.
        provider: Which LLM to use. Defaults to "anthropic".
        model: Override the default model for the chosen provider.
        max_tokens: Hard cap on the response length.
        temperature: Sampling temperature. Default 0.0 for deterministic
            structured output. Raise only when variance is wanted.

    Returns:
        An instance of `schema` populated from the LLM response.

    Raises:
        ValueError: If the response is empty or not valid JSON.
        pydantic.ValidationError: If the JSON does not match `schema`.
        anthropic.APIError / openai.APIError: For provider-side issues.
    """
    if provider == "anthropic":
        raw = _call_anthropic(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model or DEFAULT_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    elif provider == "openai":
        raw = _call_openai(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model or DEFAULT_OPENAI_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unknown provider: {provider!r}")

    return _parse_and_validate(raw, schema)


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------


def _call_anthropic(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Send a Messages API request to Anthropic. Return raw text."""
    client = _get_anthropic_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    if not response.content:
        raise ValueError("Anthropic returned an empty response")
    block = response.content[0]
    # We only request text responses (no tool use yet), so anything
    # other than a text block indicates something has changed and we
    # should fail loudly rather than silently mishandle it.
    if getattr(block, "type", None) != "text":
        raise ValueError(
            f"Anthropic returned unexpected block type: "
            f"{getattr(block, 'type', '<unknown>')}"
        )
    return block.text


def _call_openai(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Send a Chat Completions request to OpenAI in JSON mode. Return raw text."""
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("OpenAI returned an empty response")
    return content


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


def _parse_and_validate(raw: str, schema: type[T]) -> T:
    """Tolerate code fences, parse JSON, validate against the schema."""
    cleaned = raw.strip()

    # Strip optional ```json ... ``` fences. Models occasionally add
    # them despite explicit instructions not to. Stripping is harmless
    # if absent.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n", "", cleaned)
        cleaned = re.sub(r"\n```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            "LLM did not return valid JSON. First 200 chars of response: "
            f"{cleaned[:200]!r}"
        ) from e

    return schema.model_validate(data)