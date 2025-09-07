// --- small helpers -----------------------------------------------------------

function $(id) {
  return document.getElementById(id);
}

function setSpinner(spinnerEl, on) {
  if (!spinnerEl) return;
  spinnerEl.style.display = on ? "block" : "none";
}

function setStatus(statusEl, text) {
  if (!statusEl) return;
  statusEl.textContent = text || "";
}

// POST with a client-side timeout so spinners don't hang forever
async function postJSON(url, body, timeoutMs = 35000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal
    });
    return res;
  } finally {
    clearTimeout(id);
  }
}

// LocalStorage QoL: persist textarea inputs
(function initPersistence() {
  const jdEl = $("jobDesc");
  const rsEl = $("resume");
  if (jdEl) jdEl.value = localStorage.getItem("rr_jobDesc") || "";
  if (rsEl) rsEl.value = localStorage.getItem("rr_resume") || "";

  [jdEl, rsEl].forEach((el) => {
    if (!el) return;
    el.addEventListener("input", () => {
      localStorage.setItem(el.id === "jobDesc" ? "rr_jobDesc" : "rr_resume", el.value);
    });
  });
})();

// --- Resume Rewrite ----------------------------------------------------------

async function rewriteResume() {
  const jobDesc = $("jobDesc").value.trim();
  const resume = $("resume").value.trim();
  const resultBox = $("result");
  const spinnerRewrite = $("spinnerRewrite");
  const statusMessageRewrite = $("statusMessageRewrite");
  const copyBtn = $("copyBtn");
  const rewriteBtn = $("rewriteBtn");

  // basic input checks (helps avoid server 400 + huge token costs)
  if (!jobDesc || !resume) {
    alert("Please fill in both job description and resume to rewrite.");
    return;
  }
  if (resume.length < 40) {
    alert("Please paste at least one full section (40+ characters) to rewrite.");
    return;
  }

  try {
    if (rewriteBtn) rewriteBtn.disabled = true;
    setSpinner(spinnerRewrite, true);
    setStatus(statusMessageRewrite, "Contacting server...");
    if (resultBox) resultBox.innerHTML = "";
    if (copyBtn) copyBtn.style.display = "none";

    const response = await postJSON("/rewrite", {
      job_description: jobDesc,
      resume_text: resume
    });

    let json;
    try {
      json = await response.json();
    } catch {
      json = { error: "Malformed JSON from server." };
    }

    if (!response.ok) {
      setStatus(statusMessageRewrite, `❌ Error: ${json.error || "Unexpected error."}`);
      return;
    }

    const html = (json && json.rewritten_html || "").trim();
    if (resultBox) {
      resultBox.innerHTML = html
        ? html
        : "<p><em>No formatted content returned. Try a smaller section of your resume.</em></p>";
    }
    setStatus(statusMessageRewrite, "✅ Resume rewritten successfully!");
    if (copyBtn) copyBtn.style.display = "inline-block";
  } catch (err) {
    console.error(err);
    setStatus(statusMessageRewrite, "❌ Error: Could not contact server.");
  } finally {
    setSpinner(spinnerRewrite, false);
    if (rewriteBtn) rewriteBtn.disabled = false;
  }
}

// --- Clipboard ---------------------------------------------------------------

async function copyToClipboard() {
  const resultBox = $("result");
  if (!resultBox) return;

  const html = resultBox.innerHTML || "";
  const plain = resultBox.innerText || "";

  const btn = $("copyBtn");
  const done = () => {
    if (btn) {
      btn.textContent = "✅ Copied!";
      setTimeout(() => (btn.textContent = "📋 Copy to Clipboard"), 2000);
    }
  };

  // Prefer the modern async clipboard API so we copy HTML and plain text
  try {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" })
      })
    ]);
    done();
    return;
  } catch (e) {
    console.warn("Clipboard API failed, falling back to execCommand:", e);
  }

  // Fallback for older browsers
  try {
    const range = document.createRange();
    range.selectNodeContents(resultBox);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("copy");
    sel.removeAllRanges();
    done();
  } catch (e) {
    console.error("Legacy copy fallback failed:", e);
    if (btn) btn.textContent = "❌ Copy failed";
  }
}

// --- MatchMeter --------------------------------------------------------------

async function runMatchMeter() {
  const jobDesc = $("jobDesc").value.trim();
  const resume = $("resume").value.trim();
  const outputBox = $("matchMeterOutput");
  const spinner = $("spinner");
  const status = $("statusMessage");
  const lowWarning = $("lowMatchWarning");
  const rewriteBtn = $("rewriteBtn");
  const analyzeBtn = document.querySelector('button[onclick="runMatchMeter()"]'); // optional disable

  if (!jobDesc || !resume) {
    alert("Please fill in both job description and resume to analyze.");
    return;
  }

  try {
    if (analyzeBtn) analyzeBtn.disabled = true;
    setSpinner(spinner, true);
    setStatus(status, "🔍 Analyzing alignment...");
    if (outputBox) outputBox.innerHTML = "";

    const response = await postJSON("/matchmeter", {
      job_description: jobDesc,
      resume_text: resume
    });

    let json;
    try {
      json = await response.json();
    } catch {
      json = { error: "Malformed JSON from server." };
    }

    if (!response.ok) {
      if (outputBox) {
        outputBox.innerHTML = `❌ Error: ${json.error || "Unexpected error."}`;
      }
      return;
    }

    const html = (json && json.feedback_html || "").trim();
    if (outputBox) {
      outputBox.innerHTML = html ? html : "<p><em>No feedback returned.</em></p>";
    }

    const score = parseFloat(json.score);
    if (!Number.isNaN(score) && lowWarning && rewriteBtn) {
      if (score < 5) {
        lowWarning.style.display = "block";
        rewriteBtn.disabled = true;
      } else {
        lowWarning.style.display = "none";
        rewriteBtn.disabled = false;
      }
    }
    setStatus(status, "✅ Analysis complete");
  } catch (err) {
    console.error(err);
    if (outputBox) outputBox.innerHTML = "❌ Error: Could not contact server.";
  } finally {
    setSpinner(spinner, false);
    if (analyzeBtn) analyzeBtn.disabled = false;
  }
}

// Expose functions to the global scope for inline onclick handlers in index.html
window.rewriteResume = rewriteResume;
window.copyToClipboard = copyToClipboard;
window.runMatchMeter = runMatchMeter;
