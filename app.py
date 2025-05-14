import os
import re
import logging
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set in environment")

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or os.urandom(24).hex()

# ─── Flask App Setup ─────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET_KEY

# ─── OpenAI Client ───────────────────────────────────────────────────────────
client = OpenAI(api_key=OPENAI_API_KEY)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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

    # Force preservation markers
    prompt = (
        "You are an expert resume writer. You must PRESERVE ALL LINES IN THE INPUT THAT MATCH a work history entry pattern. "
        "Specifically, any lines matching '^[A-Za-z].*\\[' OR '^• ' OR section headings should be output exactly as-is, without any change.\n\n"
        "Between those preserved lines, rewrite each bullet point for clarity, impact, and ATS optimization. "
        "Do NOT remove, merge, collapse, or drop any details, dates, employers, or locations. "
        "Maintain the input order and formatting of work history lines.\n\n"
        f"Job Description:\n{job_desc}\n\n"
        f"Original Resume Text (preserve history lines exactly):\n{original}\n\n"
        "Output minimal valid HTML: ensure each job title line is in <p><strong>…</strong></p>, section headings likewise, and wrap bullets in <ul><li>…</li></ul>."
    )

    logging.info("Submitting rewrite request with enforced preservation prompt on GPT-4.1 Mini...")
    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000
        )
        html_out = resp.choices[0].message.content.strip()
        return jsonify(rewritten_html=html_out)
    except Exception as e:
        logging.error("Error in /rewrite:", exc_info=e)
        return jsonify(error="OpenAI request failed. Please try again later."), 500

@app.route("/matchmeter", methods=["POST"])
def match_meter():
    data = request.json or {}
    jd   = data.get("job_description", "").strip()
    rs   = data.get("resume_text", "").strip()
    if not jd or not rs:
        return jsonify(error="Both job description and resume are required."), 400

    prompt = (
        "You are a careful career coach. ONLY use the facts provided—do NOT hallucinate.\n"
        "First line: output ONLY your fit score as X/10.\n"
        "Then output minimal semantic HTML: wrap each subhead in <p><strong>…</strong></p> and bullets in <ul><li>…</li></ul>.\n\n"
        f"Job Description:\n{jd}\n\n"
        f"Resume:\n{rs}\n\n"
        "Begin now:"
    )
    logging.info("Submitting matchmeter request on GPT-4.1 Mini...")
    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=512
        )
        html_out = resp.choices[0].message.content.strip()
        match = re.search(r"(\d+(?:\.\d+)?)/10", html_out)
        score = match.group(1) if match else "0"
        return jsonify(score=score, feedback_html=html_out)
    except Exception as e:
        logging.error("Error in /matchmeter:", exc_info=e)
        return jsonify(error="OpenAI request failed. Please try again later."), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
