# Front-end updates required:
# - In index.html:
#     * Add a container with id="rewritten-resume" to display the HTML version of the rewritten resume.
# - In script.js:
#     * After receiving the JSON response, set innerHTML of that container using `data.rewritten_html`.

import os
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

    # Prompt model to emit HTML only: name & contact bold, headings bold, bullets lists, body paragraphs plain
    prompt = (
        "You are an expert resume writer. ONLY use the facts below—do NOT fabricate any details.\n"
        "Include the candidate’s full name and contact information exactly as provided at the very top, wrapped in <p><strong>...<strong></p>.\n"
        "Then output the rewritten resume as minimal semantic HTML only, following these rules:\n"
        "1. Do NOT wrap any body paragraph text in <strong>—only headings and the name/contact block are bold.\n"
        "2. Wrap section headings (e.g. Profile, Work Experience, Education) in <p><strong>Section Name</strong></p>.\n"
        "3. Under each heading, list bullets inside a <ul> with plain <li> items—no additional tags.\n"
        "4. Wrap any standalone paragraphs (e.g. summary) in plain <p>...<p> with no bold.\n"
        "5. Do not include any extra HTML tags or inline styles.\n\n"
        f"Job Description:\n{job_desc}\n\n"
        f"Original Resume:\n{original}\n\n"
        "Begin rewriting:" 
    )
    logging.debug("Rewrite Prompt:\n%s", prompt)
    try:
        resp = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role":"user","content":prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        html_out = resp.choices[0].message.content.strip()
        logging.debug("Rewritten Resume HTML:\n%s", html_out)
        return jsonify(rewritten_html=html_out)
    except Exception as e:
        logging.error("Error in /rewrite:", exc_info=e)
        return jsonify(error="GPT-4 failed. Please try again later."), 500

@app.route("/matchmeter", methods=["POST"])
def match_meter():
    data = request.json or {}
    jd   = data.get("job_description", "").strip()
    rs   = data.get("resume_text", "").strip()
    if not jd or not rs:
        return jsonify(error="Both job description and resume are required."), 400

    # Prompt model to emit HTML only for gap analysis
    prompt = (
        "You are a careful career coach. ONLY use the facts below—do NOT hallucinate.\n"
        "On the FIRST LINE, output ONLY your fit score as X/10 with NO extra text.\n"
        "Then emit HTML only, following these rules:\n"
        "1. Wrap each subhead (Positive Matches, Gaps and Feedback, Recommendations) in <p><strong>Subhead</strong></p>.\n"
        "2. Under each subhead, list items inside a <ul> of <li> bullets—no bold or extra tags.\n"
        "3. Do not wrap any other text in <strong>.\n"
        "4. Do not include any other tags or styling.\n\n"
        f"Job Description:\n{jd}\n\n"
        f"Resume:\n{rs}\n\n"
        "Begin now:" 
    )
    logging.debug("MatchMeter Prompt:\n%s", prompt)
    try:
        resp = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role":"user","content":prompt}],
            temperature=0.5,
            max_tokens=900
        )
        html_out = resp.choices[0].message.content.strip()
        logging.debug("MatchMeter HTML:\n%s", html_out)
        match = re.search(r"(\d+(?:\.\d+)?)/10", html_out)
        score = match.group(1) if match else "0"
        return jsonify(score=score, feedback_html=html_out)
    except Exception as e:
        logging.error("Error in /matchmeter:", exc_info=e)
        return jsonify(error="GPT-4 failed. Please try again later."), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
