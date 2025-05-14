// static/script.js

// Helper to mark a step complete or active
function mark(stepId, isActive) {
  const el = document.getElementById(stepId);
  if (!el) return;
  el.classList.toggle("fw-bold", isActive);
  el.classList.toggle("text-primary", isActive);
  el.classList.toggle("text-muted", !isActive);
}

// Minimum score before allowing a rewrite
let MIN_MATCH_SCORE = 5;

// Run MatchMeter (Gap Analysis) with animated thinking bar
async function runMatchMeter() {
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resume = document.getElementById("resume").value.trim();
  const output = document.getElementById("matchMeterOutput");
  const rewriteBtn = document.getElementById("rewriteBtn");
  const warning = document.getElementById("lowMatchWarning");

  if (!jobDesc || !resume) {
    alert("Please fill in both job description and resume fields.");
    return;
  }

  // Reset UI and show thinking bar
  output.innerHTML = `
    <div class="match-meter mt-3">
      <h5><strong>MatchMeter Thinking...</strong></h5>
      <div class="progress" style="height: 20px; background: #e9ecef;">
        <div class="progress-bar" role="progressbar" style="width: 0%; background-color: #3498db;"></div>
      </div>
    </div>
  `;
  warning.style.display = "none";
  rewriteBtn.disabled = true;

  // Animate the thinking bar back and forth
  const bar = output.querySelector('.progress-bar');
  let width = 0;
  let direction = 1;
  const animate = () => {
    width += direction * 5;
    if (width >= 100) direction = -1;
    if (width <= 0) direction = 1;
    bar.style.width = width + "%";
  };
  const intervalId = setInterval(animate, 100);

  try {
    const res = await fetch("/matchmeter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDesc, resume_text: resume })
    });
    const json = await res.json();

    clearInterval(intervalId);

    if (!res.ok) {
      output.innerHTML = `<p class="text-danger"><strong>Error:</strong> ${json.error}</p>`;
      return;
    }

    const score = parseFloat(json.score) || 0;
    let feedbackHTML = json.feedback_html || "";
    feedbackHTML = feedbackHTML.replace(/^\s*\d{1,2}\/10\s*/m, "");

    // Warn & disable rewrite if score < threshold
    if (score < MIN_MATCH_SCORE) {
      warning.style.display = "block";
      rewriteBtn.disabled = true;
    } else {
      warning.style.display = "none";
      rewriteBtn.disabled = false;
    }

    // Determine bar color
    let barColor;
    if (score <= 2) barColor = "#f44336";
    else if (score <= 5) barColor = "#ff9800";
    else if (score <= 7) barColor = "#ffeb3b";
    else barColor = "#4caf50";

    const pct = Math.min(Math.max(score * 10, 0), 100);

    // Render final gauge and feedback
    output.innerHTML = `
      <div class="match-meter mt-3">
        <h5><strong>MatchMeter Score: ${score}/10</strong></h5>
        <div class="progress" style="height: 20px; background: #e9ecef;">
          <div class="progress-bar" role="progressbar" style="width: ${pct}%; background-color: ${barColor};"></div>
        </div>
      </div>
      <div class="mt-3 report-section">${feedbackHTML}</div>
    `;
  } catch (err) {
    clearInterval(intervalId);
    output.innerHTML = `<p class="text-danger"><strong>Error contacting API:</strong> ${err.message}</p>`;
  }
}

// Rewrite Resume
async function rewriteResume() {
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resumeTxt = document.getElementById("resume").value.trim();
  const resultBox = document.getElementById("result");
  const spinnerText = document.getElementById("loading-text");

  const phrases = [
    "Polishing professional points…",
    "Refining résumé readability…",
    "Boosting bullet brilliance…",
    "Aligning accomplishments accurately…",
    "Structuring success stories…",
    "Curating career clarity…",
    "Enhancing experience excerpts…",
    "Formatting for focus…",
    "Elevating employment entries…",
    "Sharpening skills showcase…",
    "Perfecting professional profile…",
    "Highlighting hiring highlights…"
  ];
  let idx = 0;
  let rotateInterval;

  if (!jobDesc || !resumeTxt) {
    alert("Please fill in both job description and resume fields before rewriting.");
    return;
  }

  document.getElementById("spinner").style.display = "block";
  spinnerText.textContent = phrases[idx++];
  rotateInterval = setInterval(() => { spinnerText.textContent = phrases[idx % phrases.length]; idx++; }, 2000);

  resultBox.innerHTML = "";

  try {
    const res = await fetch("/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDesc, resume_text: resumeTxt })
    });
    const json = await res.json();

    if (!res.ok) {
      resultBox.innerHTML = `<p class="text-danger"><strong>Error:</strong> ${json.error}</p>`;
      return;
    }

    let html = json.rewritten_html || "";
    html = html.replace(/^```html\s*/, "").replace(/```\s*$/, "");
    resultBox.innerHTML = html;
    document.getElementById("copyBtn").style.display = "inline-block";
  } catch (err) {
    resultBox.innerHTML = `<p class="text-danger"><strong>Error contacting API:</strong> ${err.message}</p>`;
  } finally {
    document.getElementById("spinner").style.display = "none";
    clearInterval(rotateInterval);
    spinnerText.textContent = "";
  }
}

// Copy to Clipboard
function copyToClipboard() {
  const resultBox = document.getElementById("result");
  const range = document.createRange();
  range.selectNodeContents(resultBox);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand("copy");

  const btn = document.getElementById("copyBtn");
  btn.textContent = "✅ Copied!";
  setTimeout(() => btn.textContent = "📋 Copy to Clipboard", 2000);
}
