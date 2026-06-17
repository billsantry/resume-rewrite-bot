# FedCert

**Agentic federal job-matching tool that ranks only the USAJobs postings you are actually eligible to win.**

FedCert reads a resume the way a federal HR specialist would, then returns a small, honest, ranked list of currently open federal job postings with eligibility tags and one-sentence reasons drawn from your actual resume content. It is built for calibrated, honest scoring rather than inflated match rates. Built with Claude and OpenAI.

---

## How It Works

FedCert runs one structured session per resume. It is not a chatbot. You paste a resume and an optional plain-language preference, and it produces a single ranked result set, then stops.

Each session follows a three-tool pipeline (`cert/tools/registry.py`):

1. **parse_resume(resume_text)** runs once to build a structured `CandidateProfile` that every later decision depends on.
2. **search_usajobs(params)** runs 1 to 3 times, querying the USAJobs API (`data.usajobs.gov`) with parameters derived from the profile and your preference.
3. **score_match(profile, listing)** runs once per listing (up to 25, after deduplication) to produce a calibrated `MatchScore` with an eligibility tag and a one-sentence rationale.

The orchestration rules live in human-readable form in `prompts/agent_system.md`. Today `app.py` follows those rules imperatively. The design lets the same prompt and tool registry drop into an agentic tool-use API (Anthropic tool use or the OpenAI Responses API) without a code rewrite.

---

## Architecture

- **Backend:** Python, Flask. The `/cert/run` endpoint accepts `{"resume_text", "user_prompt"}` and returns a structured `SessionResult`.
- **Agent core:** `cert/agent.py` orchestrator, `cert/schemas.py` Pydantic models, `cert/services/` (resume parser, USAJobs search, match scorer), and `cert/tools/registry.py`.
- **LLM layer:** `cert/llm.py` is the only module that imports a model SDK. It returns Pydantic-validated structured output and defaults to Anthropic `claude-sonnet-4-6`, with OpenAI `gpt-4o-mini` available as a second provider.
- **Prompts:** versioned Markdown in `prompts/` (`agent_system.md`, `resume_parser.md`, `matchmeter_v2.md`).
- **Frontend:** HTML, CSS, JavaScript (`templates/index.html`, `static/`, `script.js`).

---

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure keys** in a `.env` file at the project root:
   ```ini
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   USAJOBS_API_KEY=...
   USAJOBS_USER_EMAIL=you@example.com
   ```
   The USAJobs API requires both the key and the email address that registered it. Get a key at https://developer.usajobs.gov/.
3. **Run the server:**
   ```bash
   python app.py
   ```
   The app binds to `127.0.0.1:5001` by default (override with `FLASK_HOST` and `PORT`).
4. **Open** http://127.0.0.1:5001/, paste a resume and an optional preference, and run a session.

---

## License

MIT License. Contributions welcome.
