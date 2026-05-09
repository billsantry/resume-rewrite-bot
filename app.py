import os
import logging

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# FedCert agent orchestrator
from cert.agent import run_session

# ─── Setup ─────────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")

# Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/cert/run", methods=["POST"])
def cert_run():
    """Run a complete FedCert session.

    Expects JSON: {"resume_text": str, "user_prompt": str | null}
    Returns: SessionResult JSON (see cert.schemas).
    """
    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "Request body must be JSON"}), 400

    resume_text = (body.get("resume_text") or "").strip()
    user_prompt = body.get("user_prompt") or None

    if not resume_text:
        return jsonify({"error": "resume_text is required"}), 400

    try:
        result = run_session(resume_text=resume_text, user_prompt=user_prompt)
    except RuntimeError as e:
        # Auth issues, missing env vars, etc. — actionable for the operator,
        # opaque to the end user.
        app.logger.error("FedCert run failed: %s", e)
        return jsonify({"error": "FedCert is temporarily unavailable."}), 503
    except Exception as e:
        app.logger.exception("FedCert run crashed: %s", e)
        return jsonify({"error": "Something went wrong running FedCert."}), 500

    # Pydantic model_dump() gives us a clean JSON-ready dict
    return jsonify(result.model_dump()), 200


# ─── Dev/Prod server bind ──────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)