
async function rewriteResume() {
  const apiKey = document.getElementById("apiKey").value.trim();
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resume = document.getElementById("resume").value.trim();
  const resultBox = document.getElementById("result");
  const spinner = document.getElementById("spinner");
  const status = document.getElementById("status");
  const copyBtn = document.getElementById("copyBtn");

  if (!apiKey || !jobDesc || !resume) {
    alert("Please fill in all fields including your API key.");
    return;
  }

  const prompt = `Rewrite the following resume bullet points to better match this job description. Use a professional tone, highlight relevant skills, and make them ATS-friendly.

Job Description:
${jobDesc}

Resume:
${resume}

Rewritten Resume:`;

  try {
    spinner.style.display = "block";
    status.textContent = "Contacting OpenAI API...";
    resultBox.innerHTML = "";
    copyBtn.style.display = "none";

    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + apiKey
      },
      body: JSON.stringify({
        model: "gpt-4",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.7
      })
    });

    const data = await response.json();
    spinner.style.display = "none";

    if (!response.ok) {
      status.textContent = `❌ Error: ${data.error?.message || "Unexpected response from OpenAI API."}`;
      return;
    }

    if (data.choices && data.choices.length > 0) {
      const rawText = data.choices[0].message.content.trim();
      const formattedHTML = formatResumeOutput(rawText);
      resultBox.innerHTML = formattedHTML;
      status.textContent = "✅ Response received!";
      copyBtn.style.display = "inline-block";
    } else {
      resultBox.textContent = "No response received. Check your API key or input format.";
      status.textContent = "⚠️ No response from API.";
    }

  } catch (err) {
    spinner.style.display = "none";
    status.textContent = "❌ Error: Could not reach OpenAI API.";
    console.error("Fetch error:", err);
  }
}

function copyToClipboard() {
  const resultBox = document.getElementById("result");
  const range = document.createRange();
  range.selectNodeContents(resultBox);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  document.execCommand("copy");

  const btn = document.getElementById("copyBtn");
  btn.textContent = "✅ Copied!";
  setTimeout(() => btn.textContent = "📋 Copy to Clipboard", 2000);
}

function formatResumeOutput(text) {
  const lines = text.split("\n");
  let html = "";
  let inList = false;

  const sectionHeadings = [
    "Professional Summary", "Summary", "Professional Experience", "Experience",
    "Education", "Education & Certifications", "Certifications", "Skills",
    "Technical Skills", "Key Competencies", "Projects", "Recognition & Thought Leadership",
    "Awards", "Professional Affiliations", "Federal Hiring Considerations"
  ];

  lines.forEach(line => {
    const trimmed = line.trim();

    if (!trimmed) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      return;
    }

    if (/^[-•o]/.test(trimmed)) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${trimmed.replace(/^[-•o]\s*/, "")}</li>`;
      return;
    }

    if (inList) {
      html += "</ul>";
      inList = false;
    }

    const isHeading = sectionHeadings.some(h => trimmed.toLowerCase() === h.toLowerCase());

    if (isHeading) {
      html += `<p><strong>${trimmed}</strong></p>`;
    } else {
      html += `<p>${trimmed}</p>`;
    }
  });

  if (inList) html += "</ul>";
  return html;
}

async function runMatchMeter() {
  const apiKey = document.getElementById("apiKey").value.trim();
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resume = document.getElementById("resume").value.trim();
  const outputBox = document.getElementById("matchMeterOutput");

  if (!apiKey || !jobDesc || !resume) {
    alert("Please fill in all fields to run MatchMeter.");
    return;
  }

  const prompt = `Analyze the following resume content and job description. Assign a fit score between 1 and 10 based on alignment of responsibilities, required skills, experience level, and relevant accomplishments.

If the score is below 6, list the most important gaps or mismatches, and then give a short, friendly message advising the user whether to revise their resume or look for a closer match.

Output format:
Score: [1–10]
Gaps:
- [gap 1]
- [gap 2]
Message: [constructive feedback]

Resume:
${resume}

Job Description:
${jobDesc}`;

  try {
    outputBox.innerHTML = "🔍 Analyzing alignment...";
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + apiKey
      },
      body: JSON.stringify({
        model: "gpt-4",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.3
      })
    });

    const data = await response.json();
    if (data.choices && data.choices.length > 0) {
      const text = data.choices[0].message.content.trim();

      const scoreMatch = text.match(/Score:\s*([\d.]+)/i);
      const score = scoreMatch ? parseFloat(scoreMatch[1]) : null;

      const messageMatch = text.match(/Message:\s*(.+)/is);
      const message = messageMatch ? messageMatch[1].trim() : "";

      const gapLines = text.match(/- .+/g) || [];

      const gapList = gapLines.length
        ? `<ul>${gapLines.map(g => `<li>${g.replace(/^- /, '')}</li>`).join('')}</ul>`
        : "<p>No significant gaps detected.</p>";

      const leftPercent = ((score - 1) / 9) * 100;

      const html = `
        <div class="matchmeter-score">MatchMeter Score: <strong>${score}</strong></div>
        <div class="matchmeter-marker">
          ${Array.from({ length: 10 }, (_, i) => `<span>${i + 1}</span>`).join('')}
        </div>
        <div class="matchmeter-bar">
          <div class="matchmeter-indicator" style="left:${leftPercent}%;"></div>
        </div>
        <p><strong>Assessment:</strong> ${message}</p>
        <p><strong>Gaps:</strong></p>
        ${gapList}
      `;

      outputBox.innerHTML = html;
    } else {
      outputBox.innerHTML = "⚠️ No response received from MatchMeter.";
    }
  } catch (error) {
    console.error("MatchMeter error:", error);
    outputBox.innerHTML = "❌ Error contacting OpenAI API for MatchMeter.";
  }
}
