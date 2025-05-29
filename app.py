import os
import json
import re
import logging
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# ─── Setup ─────────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

MODEL = "gpt-4.1"

def render_resume_html(parsed):
    html = []
    # Name & contact
    html.append(f"<p><strong>{parsed['name_contact']}</strong></p>")
    for section in parsed["sections"]:
        if "heading" in section:
            html.append(f"<p><strong>{section['heading']}</strong></p>")
        # Paragraphs (e.g. summary)
        for para in section.get("paragraphs", []):
            html.append(f"<p>{para}</p>")
        # Work items
        for item in section.get("items", []):
            title_line = f"{item['title']}, {item['company']} | {item['dates']}"
            html.append(f"<p>{title_line}</p>")
            html.append("<ul>")
            for b in item["bullets"]:
                html.append(f"<li>{b}</li>")
            html.append("</ul>")
        # Other list items (e.g. skills)
        if "list_items" in section:
            html.append("<ul>")
            for li in section["list_items"]:
                html.append(f"<li>{li}</li>")
            html.append("</ul>")
    return "\n".join(html)

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/rewrite", methods=["POST"])
def rewrite_resume():
    data     = request.json or {}
    job_desc = data.get("job_description", "").strip()
    original = data.get("resume_text", "").strip()
    if not original:
        return jsonify(error="No resume text provided."), 400

    try:
        # Phase 1: Parse the resume into structured JSON
        parse_resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role":"system","content":"You are a resume parser."},
                {"role":"user","content":f"Parse this resume into JSON:\n```\n{original}\n```"}
            ],
            functions=[{
                "name": "parse_resume",
                "description": "Parse a plain-text resume into structured JSON",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name_contact": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "heading": {"type": "string"},
                                    "paragraphs": {"type": "array", "items": {"type": "string"}},
                                    "items": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "title": {"type": "string"},
                                                "company": {"type": "string"},
                                                "dates": {"type": "string"},
                                                "bullets": {"type": "array", "items": {"type": "string"}}
                                            }
                                        }
                                    },
                                    "list_items": {"type": "array", "items": {"type": "string"}}
                                }
                            }
                        }
                    },
                    "required": ["name_contact", "sections"]
                }
            }],
            function_call={"name": "parse_resume"}
        )
        parsed_args = parse_resp.choices[0].message.function_call.arguments
        parsed = json.loads(parsed_args)
        logging.debug("Parsed resume JSON:\n%s", json.dumps(parsed, indent=2))

        # Phase 2: Rewrite only the bullets
        rewrite_resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role":"system","content":"You are an expert résumé editor that only returns JSON."},
                {"role":"user","content":(
                    "Rewrite **only** the `bullets` arrays in this resume JSON to better match "
                    "the job description below. Preserve all other fields exactly and return "
                    "the full JSON.\n\n"
                    f"Job Description:\n{job_desc}\n\n"
                    f"Resume JSON:\n{json.dumps(parsed)}"
                )}
            ],
            functions=[{
                "name": "rewrite_bullets",
                "description": "Rewrite the bullets in the resume JSON without changing other fields",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name_contact": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type":"object",
                                "properties": {
                                    "heading": {"type":"string"},
                                    "paragraphs": {"type":"array","items":{"type":"string"}},
                                    "items": {
                                        "type":"array",
                                        "items": {
                                            "type":"object",
                                            "properties": {
                                                "title":{"type":"string"},
                                                "company":{"type":"string"},
                                                "dates":{"type":"string"},
                                                "bullets":{"type":"array","items":{"type":"string"}}
                                            }
                                        }
                                    },
                                    "list_items": {"type":"array","items":{"type":"string"}}
                                }
                            }
                        }
                    },
                    "required": ["name_contact", "sections"]
                }
            }],
            function_call={"name": "rewrite_bullets"},
            temperature=0.2,
            max_tokens=2000
        )
        rewritten_args = rewrite_resp.choices[0].message.function_call.arguments
        rewritten = json.loads(rewritten_args)
        logging.debug("Rewritten resume JSON:\n%s", json.dumps(rewritten, indent=2))

        # Render to HTML and return
        html_out = render_resume_html(rewritten)
        return jsonify(rewritten_html=html_out)

    except Exception as e:
        logging.exception("Error during resume rewriting process.")
        return jsonify(error="Sorry, we hit a snag rewriting the resume. Try again!"), 500

@app.route("/matchmeter", methods=["POST"])
def match_meter():
    data = request.json or {}
    jd   = data.get("job_description", "").strip()
    rs   = data.get("resume_text", "").strip()
    if not jd or not rs:
        return jsonify(error="Both job description and resume are required."), 400

    prompt = (
        "You are a careful career coach. ONLY use the facts below—do NOT hallucinate.\n"
        "On the FIRST LINE, output ONLY your fit score as X/10 with NO extra text.\n"
        "Then emit HTML only, following these rules:\n"
        "1. Wrap each subhead (Positive Matches, Gaps and Feedback, Recommendations)\n"
        "   in <p><strong>Subhead</strong></p>.\n"
        "2. Under each subhead, list items inside a <ul> of <li> bullets—no extra tags.\n"
        "3. Do not wrap any other text in <strong>.\n"
        "4. Do not include any other tags or styling.\n\n"
        f"Job Description:\n{jd}\n\n"
        f"Resume:\n{rs}\n\n"
        "Begin now:"
    )
    logging.debug("MatchMeter Prompt:\n%s", prompt)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"user","content":prompt}],
        temperature=0.5,
        max_tokens=900
    )
    html_out = resp.choices[0].message.content.strip()
    match = re.search(r"(\d+(?:\.\d+)?)/10", html_out)
    score = match.group(1) if match else "0"
    return jsonify(score=score, feedback_html=html_out)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
