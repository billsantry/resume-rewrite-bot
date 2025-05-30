async function rewriteResume() {
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resume = document.getElementById("resume").value.trim();
  const resultBox = document.getElementById("result");
  const spinnerRewrite = document.getElementById("spinnerRewrite");
  const statusMessageRewrite = document.getElementById("statusMessageRewrite");
  const copyBtn = document.getElementById("copyBtn");

  if (!jobDesc || !resume) {
    alert("Please fill in both job description and resume to rewrite.");
    return;
  }

  try {
    spinnerRewrite.style.display = "block";
    statusMessageRewrite.textContent = "Contacting server...";
    resultBox.innerHTML = "";
    copyBtn.style.display = "none";

    const response = await fetch("/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDesc, resume_text: resume })
    });

    const json = await response.json();
    spinnerRewrite.style.display = "none";

    if (!response.ok) {
      statusMessageRewrite.textContent = `❌ Error: ${json.error || "Unexpected error."}`;
      return;
    }

    resultBox.innerHTML = json.rewritten_html;
    statusMessageRewrite.textContent = "✅ Resume rewritten successfully!";
    copyBtn.style.display = "inline-block";
  } catch (err) {
    spinnerRewrite.style.display = "none";
    statusMessageRewrite.textContent = "❌ Error: Could not contact server.";
    console.error(err);
  }
}

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

async function runMatchMeter() {
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resume = document.getElementById("resume").value.trim();
  const outputBox = document.getElementById("matchMeterOutput");
  const spinner = document.getElementById("spinner");
  const status = document.getElementById("statusMessage");
  const lowWarning = document.getElementById("lowMatchWarning");
  const rewriteBtn = document.getElementById("rewriteBtn");

  if (!jobDesc || !resume) {
    alert("Please fill in both job description and resume to analyze.");
    return;
  }

  spinner.style.display = "block";
  status.textContent = "🔍 Analyzing alignment...";
  outputBox.innerHTML = "";

  try {
    const response = await fetch("/matchmeter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDesc, resume_text: resume })
    });

    const json = await response.json();
    spinner.style.display = "none";

    if (!response.ok) {
      outputBox.innerHTML = `❌ Error: ${json.error || "Unexpected error."}`;
      return;
    }

    outputBox.innerHTML = json.feedback_html;
    if (parseFloat(json.score) < 5) {
      lowWarning.style.display = "block";
      rewriteBtn.disabled = true;
    } else {
      lowWarning.style.display = "none";
      rewriteBtn.disabled = false;
    }
  } catch (err) {
    spinner.style.display = "none";
    outputBox.innerHTML = "❌ Error: Could not contact server.";
    console.error(err);
  }
}
