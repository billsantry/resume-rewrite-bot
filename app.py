import os
import json
import re
import time
import logging
from typing import Any, Dict, List, Union

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# OpenAI 1.x clients
from openai import OpenAI, AzureOpenAI

# ─── Setup ─────────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")

# Provider selection: "openai" (default) or "azure"
PROVIDER = (os.getenv("PROVIDER") or "openai").strip().lower()

# Primary model / deployment (used as default/score fallback)
# - For OpenAI: use a model name e.g., "gpt-4.1"
# - For Azure: use your DEPLOYMENT NAME e.g., "gpt-4o-mini-128k-deploy"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1").strip()

# Faster per-phase models (override via env). Use deployment names on Azure.
MODEL_PARSE   = os.getenv("OPENAI_MODEL_PARSE",   "gpt-4o-mini").strip()
MODEL_REWRITE = os.getenv("OPENAI_MODEL_REWRITE", "gpt-4o-mini").strip()
MODEL_SCORE   = os.getenv("OPENAI_MODEL_SCORE",   MODEL).strip()

# Global request timeout
REQUEST_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "35"))  # seconds

# Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def make_client():
    """
    Create an OpenAI (or Azure OpenAI) client for the 1.x SDK.
    For Azure, you must set:
      AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION
    """
    if PROVIDER == "azure":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
        if not endpoint or not api_key:
            raise ValueError("For PROVIDER=azure, set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY.")
        logging.info("Using AzureOpenAI endpoint=%s api_version=%s", endpoint, api_version)
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=REQUEST_TIMEOUT,
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment.")
        logging.info("Using OpenAI (public) API")
        return OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT)

client = make_client()

# ─── Utilities ─────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        # Remove lines that are code fences like ``` or ```json
        lines = [ln for ln in t.strip("`").splitlines()
                 if not ln.strip().startswith(("```json", "```"))]
        t = "\n".join(lines).strip()
    return t

def _parse_json_lenient(text: str) -> Dict[str, Any]:
    """
    Try strict parse; if that fails, take the largest {...} region.
    Raise ValueError if we still can't parse.
    """
    t = _strip_code_fences(text)
    try:
        return json.loads(t)
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(t[start:end + 1])
    raise ValueError("Model returned non-JSON or malformed JSON.")

def _clip_text(s: str, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n[...truncated...]"

def _squash_ws(s: str) -> str:
    # collapse multi-newlines and large spaces to reduce tokenization cost
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", s or "")).strip()

def _repair_json_via_model(bad_text: str, hint: str, schema_note: str = "") -> Dict[str, Any]:
    """
    Ask the model to reformat malformed JSON; force strict JSON mode via Chat Completions.
    """
    prompt = (
        "You will receive text intended to be valid JSON but it is malformed. "
        "Return ONLY a valid JSON object that best matches the intent. "
        "Do NOT include code fences or any extra text.\n"
    )
    if schema_note:
        prompt += f"\nSchema note:\n{schema_note}\n"
    prompt += f"\nContext:\n{hint}\n\nMalformed JSON text follows:\n{bad_text}"

    fix = client.chat.completions.create(
        model=MODEL_PARSE,  # small/fast is fine for repair
        messages=[
            {"role": "system", "content": "You are a strict JSON reformatter. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=900,
    )
    fixed_text = (fix.choices[0].message.content or "").strip()
    return _parse_json_lenient(fixed_text)

def render_resume_html(parsed: Union[Dict[str, Any], str]) -> str:
    """
    Robust renderer:
    - If `parsed` is a string or unexpected shape, pretty-print as paragraphs/bullets.
    - If structured, render sections/items/bullets as before.
    """
    def _render_freeform(text: str) -> str:
        # Split into paragraphs by blank lines
        blocks = re.split(r"\n\s*\n", (text or "").strip())
        out = []
        for block in blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            # If most lines look like bullets, render as <ul>
            bulletish = [ln for ln in lines if re.match(r"^(\-|\*|•|\u2022)\s+", ln)]
            if len(bulletish) >= max(1, int(0.6 * len(lines))):
                out.append("<ul>")
                for ln in lines:
                    ln = re.sub(r"^(\-|\*|•|\u2022)\s+", "", ln).strip()
                    out.append(f"<li>{ln}</li>")
                out.append("</ul>")
            else:
                out.append(f"<p>{' '.join(lines)}</p>")
        return "\n".join(out) if out else ""

    if isinstance(parsed, str):
        return _render_freeform(parsed)

    if not isinstance(parsed, dict):
        return _render_freeform(str(parsed))

    html: List[str] = []

    name_contact = parsed.get("name_contact")
    if isinstance(name_contact, str) and name_contact.strip():
        html.append(f"<p><strong>{name_contact.strip()}</strong></p>")

    sections = parsed.get("sections")
    if not isinstance(sections, list) or not sections:
        raw = []
        for k in ("summary", "objective", "experience", "education", "skills", "projects", "raw_text"):
            v = parsed.get(k)
            if isinstance(v, str) and v.strip():
                raw.append(v.strip())
        if raw:
            html.append(_render_freeform("\n\n".join(raw)))
        else:
            html.append(_render_freeform(json.dumps(parsed, ensure_ascii=False, indent=2)))
        return "\n".join(html)

    for section in sections:
        if not isinstance(section, dict):
            if isinstance(section, str):
                html.append(_render_freeform(section))
            continue

        heading = section.get("heading")
        if isinstance(heading, str) and heading.strip():
            html.append(f"<p><strong>{heading.strip()}</strong></p>")

        paras = section.get("paragraphs") or []
        if isinstance(paras, list):
            for para in paras:
                if isinstance(para, str) and para.strip():
                    html.append(f"<p>{para.strip()}</p>")

        items = section.get("items") or []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    if isinstance(item, str) and item.strip():
                        html.append(f"<p>{item.strip()}</p>")
                    continue

                parts = []
                title = item.get("title")
                company = item.get("company")
                dates = item.get("dates")
                if isinstance(title, str) and title.strip(): parts.append(title.strip())
                if isinstance(company, str) and company.strip(): parts.append(company.strip())
                if isinstance(dates, str) and dates.strip(): parts.append(dates.strip())
                if parts:
                    html.append(f"<p>{' | '.join(parts)}</p>")

                bullets = item.get("bullets") or []
                norm_bullets = []
                if isinstance(bullets, list):
                    for b in bullets:
                        if isinstance(b, str) and b.strip():
                            norm_bullets.append(b.strip())
                        elif isinstance(b, dict):
                            t = b.get("text")
                            if isinstance(t, str) and t.strip():
                                norm_bullets.append(t.strip())
                if norm_bullets:
                    html.append("<ul>")
                    for b in norm_bullets:
                        b = re.sub(r"^(\-|\*|•|\u2022)\s+", "", b).strip()
                        html.append(f"<li>{b}</li>")
                    html.append("</ul>")

                highlights = item.get("additional_highlights") or []
                if isinstance(highlights, list) and highlights:
                    html.append("<ul>")
                    for h in highlights:
                        if isinstance(h, str) and h.strip():
                            html.append(f"<li>{h.strip()}</li>")
                    html.append("</ul>")

        list_items = section.get("list_items") or []
        if isinstance(list_items, list) and list_items:
            html.append("<ul>")
            for li in list_items:
                if isinstance(li, str) and li.strip():
                    html.append(f"<li>{li.strip()}</li>")
            html.append("</ul>")

    return "\n".join(html) if html else _render_freeform(json.dumps(parsed, ensure_ascii=False))

# ─── Token-saving: bullets map extraction & merge ──────────────────────────────

def _extract_bullets_map(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for si, section in enumerate(parsed.get("sections", [])):
        items = section.get("items", []) or []
        for ii, item in enumerate(items):
            bullets = item.get("bullets") or []
            if not isinstance(bullets, list):
                continue
            entry = {"section_idx": si, "item_idx": ii, "bullets": bullets}
            if section.get("heading"): entry["heading"] = section["heading"]
            if item.get("title"): entry["title"] = item["title"]
            if item.get("company"): entry["company"] = item["company"]
            out.append(entry)
    return out

def _merge_rewritten_bullets(original: Dict[str, Any], rewritten_map: List[Dict[str, Any]]) -> Dict[str, Any]:
    sections = original.get("sections", [])
    for entry in rewritten_map:
        try:
            si = int(entry.get("section_idx"))
            ii = int(entry.get("item_idx"))
            new_bullets = entry.get("bullets")
            if (
                isinstance(new_bullets, list)
                and 0 <= si < len(sections)
                and "items" in sections[si]
                and 0 <= ii < len(sections[si]["items"])
            ):
                sections[si]["items"][ii]["bullets"] = new_bullets
        except Exception:
            continue
    original["sections"] = sections
    return original

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/rewrite", methods=["POST"])
def rewrite_resume():
    """
    SIMPLE / STABLE PATH:
    Ask the model to return FINAL HTML directly (no JSON parsing).
    Input:  { "job_description": "...", "resume_text": "..." }
    Output: { "rewritten_html": "<p>...</p><ul>...</ul>..." }
    """
    data     = request.json or {}
    job_desc = (data.get("job_description") or "").strip()
    original = (data.get("resume_text") or "").strip()

    if not original:
        return jsonify(error="No resume text provided."), 400

    # very small safe fallback so UI never shows blank
    fallback_html = (
        "<p><strong>Rewritten Resume</strong></p>"
        "<p>(Model unavailable; showing your original text.)</p>"
        f"<p>{original[:5000]}</p>"
    )

    # Minimal prompt: produce clean, semantic HTML only.
    system = (
        "You are a résumé rewriting assistant. Return ONLY clean, semantic HTML. "
        "Do not include any Markdown, code fences, or explanations—HTML only."
    )
    user = (
        "Rewrite the résumé bullets to better match the job description. "
        "Preserve facts; do not fabricate. Prefer active voice, impact, metrics, and ATS-aligned keywords.\n\n"
        "STRICT OUTPUT FORMAT (HTML ONLY):\n"
        "- Start with an optional name/contact line as a <p><strong>…</strong></p> if present.\n"
        "- For each section, render the heading in <p><strong>Heading</strong></p>.\n"
        "- Render summary or prose as <p>…</p>.\n"
        "- For jobs/education, render a title line as <p>Title | Company | Dates</p> when available.\n"
        "- Render bullets as <ul><li>…</li></ul> (no nested lists).\n"
        "- For skills/technologies, a simple <ul><li>…</li></ul> list is fine.\n"
        "- NO extra text, no backticks—HTML ONLY.\n\n"
        f"JOB DESCRIPTION:\n{job_desc[:8000]}\n\n"
        f"ORIGINAL RÉSUMÉ TEXT:\n{original[:16000]}"
    )

    try:
        # Use Chat Completions (plain text output); no JSON schema at all.
        resp = client.chat.completions.create(
            model=MODEL_REWRITE,          # e.g., gpt-4o-mini (or your Azure deployment name)
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,                # deterministic
            max_tokens=3000,              # you asked to push to ~3000
        )
        html_out = (resp.choices[0].message.content or "").strip()

        # Guardrails: if model ignored and sent code fences, strip them quickly.
        if html_out.startswith("```"):
            html_out = html_out.strip("`")
            # remove any lingering ```html / ``` markers lines
            html_out = "\n".join(
                ln for ln in html_out.splitlines()
                if not ln.strip().lower().startswith(("```html", "```"))
            ).strip()

        # Last resort if empty:
        if not html_out:
            html_out = fallback_html

        return jsonify(rewritten_html=html_out)

    except Exception:
        logging.exception("Rewrite (HTML mode) failed; returning fallback.")
        return jsonify(rewritten_html=fallback_html), 200



@app.route("/matchmeter", methods=["POST"])
def match_meter():
    """
    Input:  { "job_description": "...", "resume_text": "..." }
    Output: { "score": "X", "feedback_html": "<html...>" }
    """
    data = request.json or {}
    jd   = (data.get("job_description") or "").strip()
    rs   = (data.get("resume_text") or "").strip()
    if not jd or not rs:
        return jsonify(error="Both job description and resume are required."), 400

    # ---------- knobs ----------
    try:
        bias = int(os.getenv("MATCHMETER_BIAS", "0"))
    except Exception:
        bias = 0
    try:
        model_w = float(os.getenv("MATCHMETER_WEIGHT", "0.7"))
    except Exception:
        model_w = 0.7
    model_w = max(0.0, min(1.0, model_w))

    # ---------- heuristic overlap ----------
    def tokenize(s: str):
        toks = re.findall(r"[A-Za-z][A-Za-z0-9+\-/\.]{1,}", (s or "").lower())
        stop = {
            "and","or","the","a","an","to","of","in","on","for","with","by","as","at","is","are","be","we",
            "you","your","our","their","this","that","from","will","ability","including","using","use","etc",
            "experience","years","year","team","teams","work","working","strong","skills","skill",
            "knowledge","preferred","required","responsibilities","requirements","role","position"
        }
        return {t for t in toks if t not in stop and len(t) >= 3}

    jd_terms = tokenize(jd)
    rs_terms = tokenize(rs)
    inter = len(jd_terms & rs_terms)
    union = len(jd_terms | rs_terms) or 1
    jaccard = inter / union  # 0..1

    # Heuristic score 1..10
    import math
    heuristic_score = 1 + 9 * (1 - math.exp(-4.0 * jaccard))
    heuristic_score = max(1.0, min(10.0, heuristic_score))

    # ---------- model scoring (Responses API) ----------
    rubric = (
        "You are MatchMeter, a consistent resume-to-job fit scorer.\n"
        "STRICT FORMAT:\n"
        "Line 1: only the numeric score as X/10\n"
        "Then HTML feedback with EXACTLY these sections:\n"
        "<p><strong>Positive Matches</strong></p><ul>...</ul>\n"
        "<p><strong>Gaps and Feedback</strong></p><ul>...</ul>\n"
        "<p><strong>Recommendations</strong></p><ul>...</ul>\n\n"
        "SCORING RUBRIC:\n"
        "10/10: Direct, highly specific match; nearly all core & preferred skills with clear recent evidence.\n"
        "9/10: Strong match; most core skills + several preferred with evidence.\n"
        "8/10: Good match; core skills largely present; some preferred; reasonably recent.\n"
        "7/10: Solid candidate; ~60–70% overlap on core skills, clear adjacent experience, learnable gaps.\n"
        "6/10: Partial match; ~50–60% overlap; notable gaps but plausible ramp-up.\n"
        "5/10: Limited match; ~40–50% overlap; significant gaps or outdated evidence.\n"
        "≤4/10: Poor match; mostly unrelated or minimal evidence.\n\n"
        "INTERPRETATION:\n"
        "- Give credit for adjacent/transferable skills when clearly applicable.\n"
        "- Penalize only for material missing core requirements.\n"
        "- Prefer evidenced responsibilities, scope, outcomes over buzzwords.\n\n"
        "Now score the pair below."
    )

    jd_clip = jd if len(jd) <= 4000 else jd[:4000] + "\n\n[...truncated...]"
    rs_clip = rs if len(rs) <= 6000 else rs[:6000] + "\n\n[...truncated...]"

    prompt = (
        f"{rubric}\n\n"
        f"Job Description:\n{jd_clip}\n\n"
        f"Resume:\n{rs_clip}\n\n"
        "Begin now:"
    )

    try:
        resp = client.responses.create(
            model=MODEL_SCORE,
            input=[{"role": "user", "content": prompt}],
            max_output_tokens=900,
        )
        text_out = (resp.output_text or "").strip()
    except Exception:
        # fallback to heuristic only
        fallback_score = round(heuristic_score, 1)
        html = (
            "<p><strong>Positive Matches</strong></p><ul><li>Automated heuristic overlap detected.</li></ul>"
            "<p><strong>Gaps and Feedback</strong></p><ul><li>Model feedback unavailable; network or API issue.</li></ul>"
            "<p><strong>Recommendations</strong></p><ul><li>Try again or provide a shorter JD/resume excerpt.</li></ul>"
        )
        return jsonify(score=str(fallback_score), feedback_html=html)

    # Parse model score from first line
    first_line, _, remainder = text_out.partition("\n")
    line_for_score = first_line if first_line else text_out
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", line_for_score.replace("\u00A0", " "))
    model_score = float(m.group(1)) if m else heuristic_score

    fused = model_w * model_score + (1.0 - model_w) * heuristic_score + bias
    fused = max(1.0, min(10.0, fused))
    final_score = int(fused) if abs(fused - int(fused)) < 1e-9 else round(fused, 1)

    feedback_html = remainder.strip() if remainder else text_out.strip()
    return jsonify(score=str(final_score), feedback_html=feedback_html)


# ─── Dev/Prod server bind ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # For local dev you can keep 127.0.0.1. For Azure App Service, prefer 0.0.0.0.
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
