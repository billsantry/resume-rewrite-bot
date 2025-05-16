````markdown
# Resume Rewrite Bot

**Optimize your resume bullet points with AI for improved clarity, ATS compatibility, and job alignment.**

An open-source application that uses OpenAI to rewrite resume content, preserving every original bullet while refining language and tone. Includes a fit-score evaluator (MatchMeter) and engaging status updates during processing.

---

## Version 1.5 Highlights 🚀

- 🕒 **Status Messages:** Enjoy rotating fun messages (e.g., “Polishing those bullets…”) during processing.
- 🔨 **Backend Integration:** A lightweight Flask server (`app.py`) ensures reliable API handling.
- 🛡️ **Bullet Preservation:** Every original bullet is retained; triggers a log warning if any are dropped.
- ⚡ **MatchMeter Performance:** Powered by **gpt-3.5-turbo** for near-instant fit scoring.

---

## Key Features 🔍

- ✏️ **Automated Bullet Rewrites:** GPT-powered enhancements for each resume bullet—no merging or omissions.
- 📊 **MatchMeter Scoring:** Generates a 1–10 alignment score with detailed gap analysis and actionable recommendations.
- 💬 **Status Messages:** Lighthearted updates like “Injecting confidence into each line…” to keep you engaged.
- 🧩 **Semantic HTML Output:** Clean, copy-pasteable HTML for easy integration or export.
- 🌐 **Self-Hosted Flexibility:** Run locally or in the cloud with your own OpenAI API key.

---

## Demo 🎬

After starting the server, visit <http://localhost:5000/> in your browser. Input your job description and resume bullets to see live rewrites and fit scoring.

---

## Usage Guide 🛠️

1. **Obtain an OpenAI API Key** (see 🔑 below).
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure** your key by creating a `.env` file at the project root:
   ```ini
   OPENAI_API_KEY=sk-<YOUR_SECRET_KEY>
   ```
4. **Start the server**:
   ```bash
   export FLASK_APP=app.py   # macOS/Linux
   set FLASK_APP=app.py      # Windows PowerShell
   flask run
   ```
5. **Open the UI** at <http://127.0.0.1:5000/>.
6. **Use the application**:
   - Paste your **job description**.
   - Paste your **resume bullets**.
   - Click **Rewrite Resume** and observe the status messages.
   - (Optional) Click **Run MatchMeter** for fit scoring.
   - Copy or embed the resulting HTML output.

---

## OpenAI API Key Setup 🔑

1. Sign in at: [OpenAI API Keys](https://platform.openai.com/account/api-keys)
2. Create a new secret key.
3. Add the key to your `.env` file as shown above.

> *Note: API usage charges apply based on your OpenAI subscription.*

---

## Technology Stack 🧰

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **AI Models:** GPT-4, GPT-3.5-turbo
- **Configuration:** dotenv (for environment variables)

---

## Contribution & License 📄

This project is licensed under the **MIT License**. Contributions are welcome—please review the contributing guidelines before submitting.

---

## Acknowledgments 🙏

Developed to make resume refinement accessible to all, leveraging AI to enhance clarity and alignment without sacrificing content integrity.
````
