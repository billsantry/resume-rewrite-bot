// static/script.js

// Minimum score before allowing a rewrite
const MIN_MATCH_SCORE = 5;

// Whimsical messages for MatchMeter
const MATCH_STATUS_MESSAGES = [
  'Crunching your fit score…',
  'Aligning keywords and skills…',
  'Balancing your career equation…',
  'Measuring your match potential…',
  'Calibrating your application strength…',
  'Scouting for gaps and matches…'
];

// Whimsical messages for Resume Rewrite
const REWRITE_STATUS_MESSAGES = [
  'Polishing those bullets…',
  'Sharpening the resume scissors…',
  'Dusting off your career highlights…',
  'Injecting confidence into each line…',
  'Unleashing your inner rockstar résumé…',
  'Crafting buzzworthy bullet points…'
];

let statusInterval;

// Start rotating status messages from the given array
function startStatusMessages(container, messages) {
  let idx = 0;
  container.textContent = messages[idx];
  statusInterval = setInterval(() => {
    idx = (idx + 1) % messages.length;
    container.textContent = messages[idx];
  }, 2500);
}

// Stop rotation and clear the container
function stopStatusMessages(container) {
  clearInterval(statusInterval);
  container.textContent = '';
}

// Run MatchMeter (Gap Analysis)
async function runMatchMeter() {
  const jobDesc    = document.getElementById("jobDesc").value.trim();
  const resume     = document.getElementById("resume").value.trim();
  const output     = document.getElementById("matchMeterOutput");
  const spinner    = document.getElementById("spinner");
  const statusDiv  = document.getElementById("statusMessage");
  const rewriteBtn = document.getElementById("rewriteBtn");
  const warning    = document.getElementById("lowMatchWarning");

  if (!jobDesc || !resume) {
    alert("Please fill in both job description and resume fields.");
    return;
  }

  // Show spinner & start MatchMeter messages
  spinner.style.display = "block";
  startStatusMessages(statusDiv, MATCH_STATUS_MESSAGES);
  output.innerHTML      = "";
  warning.style.display = "none";
  rewriteBtn.disabled   = true;

  try {
    const res  = await fetch("/matchmeter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDesc, resume_text: resume })
    });
    const json = await res.json();

    if (!res.ok) {
      output.innerHTML = `<p class="text-danger"><strong>Error:</strong> ${json.error}</p>`;
      return;
    }

    const score        = parseFloat(json.score) || 0;
    const feedbackHTML = json.feedback_html || "";

    // Warn & disable rewrite if score < threshold
    if (score < MIN_MATCH_SCORE) {
      warning.style.display = "block";
      rewriteBtn.disabled   = true;
    } else {
      warning.style.display = "none";
      rewriteBtn.disabled   = false;
    }

    // Color by score bracket
    let barColor;
    if (score <= 2)      barColor = "#f44336";   // red
    else if (score <= 5) barColor = "#ff9800";   // orange
    else if (score <= 7) barColor = "#ffeb3b";   // yellow
    else                  barColor = "#4caf50";   // green

    const pct = Math.min(Math.max(score * 10, 0), 100);

    // Render gauge + server-generated feedback HTML
    output.innerHTML = `
      <div class="match-meter mt-3">
        <h5><strong>MatchMeter Score: ${score}/10</strong></h5>
        <div class="progress" style="height: 20px; background: #e9ecef;">
          <div class="progress-bar"
               role="progressbar"
               style="width: ${pct}%; background-color: ${barColor};">
          </div>
        </div>
      </div>
      <div class="mt-3 report-section">
        ${feedbackHTML}
      </div>
    `;
  } catch (err) {
    output.innerHTML = `<p class="text-danger"><strong>Error contacting API:</strong> ${err.message}</p>`;
  } finally {
    spinner.style.display = "none";
    stopStatusMessages(statusDiv);
  }
}

// Rewrite Resume
async function rewriteResume() {
  const jobDesc   = document.getElementById("jobDesc").value.trim();
  const resumeTxt = document.getElementById("resume").value.trim();
  const resultBox = document.getElementById("result");
  const spinner   = document.getElementById("spinner");
  const statusDiv = document.getElementById("statusMessage");

  if (!resumeTxt) {
    alert("Please enter your resume text.");
    return;
  }

  // Show spinner & start Rewrite messages
  spinner.style.display = "block";
  startStatusMessages(statusDiv, REWRITE_STATUS_MESSAGES);
  resultBox.innerHTML   = "";

  try {
    const res  = await fetch("/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDesc, resume_text: resumeTxt })
    });
    const json = await res.json();

    if (!res.ok) {
      resultBox.innerHTML = `<p class="text-danger"><strong>Error:</strong> ${json.error}</p>`;
      return;
    }

    // Inject the server-generated HTML
    resultBox.innerHTML = json.rewritten_html || "";
    document.getElementById("copyBtn").style.display = "inline-block";
  } catch (err) {
    resultBox.innerHTML = `<p class="text-danger"><strong>Error contacting API:</strong> ${err.message}</p>`;
  } finally {
    spinner.style.display = "none";
    stopStatusMessages(statusDiv);
  }
}

// Copy to Clipboard
function copyToClipboard() {
  const resultBox = document.getElementById("result");
  const range     = document.createRange();
  range.selectNodeContents(resultBox);
  const sel       = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand("copy");

  const btn = document.getElementById("copyBtn");
  btn.textContent = "✅ Copied!";
  setTimeout(() => btn.textContent = "📋 Copy to Clipboard", 2000);
}
