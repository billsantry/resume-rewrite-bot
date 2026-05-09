/**
 * Cert frontend.
 *
 * Wires the "Find federal jobs that match this resume" panel to the
 * /cert/run endpoint. Handles status messaging, error display, and
 * result-card rendering.
 *
 * Reads the resume text from the existing Resume Rewriter's textarea
 * (#bullets or whichever the user has populated). The optional
 * preference text comes from #certPrompt.
 */

(function () {
  "use strict";

  // ---------- Config ----------

  const STATUS_MESSAGES = [
    "Reading your resume…",
    "Checking which postings you're eligible for…",
    "Searching open federal jobs…",
    "Scoring fit against your background…",
    "Picking the strongest matches…",
  ];
  const STATUS_MESSAGE_HOLD_MS = 1800;

  // ---------- DOM helpers ----------

  function $(id) {
    return document.getElementById(id);
  }

  function show(el) {
    if (el) el.style.display = "";
  }
  function hide(el) {
    if (el) el.style.display = "none";
  }
  function setText(el, text) {
    if (el) el.textContent = text;
  }
  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ---------- Resume text resolution ----------

  function getResumeText() {
    // The existing rewriter's primary input. Adjust if your textarea has
    // a different id; common candidates are #bullets, #resume, #input.
    const candidates = ["resumeText", "bullets", "resume", "input"];
    for (const id of candidates) {
      const el = document.getElementById(id);
      if (el && el.value && el.value.trim()) {
        return el.value.trim();
      }
    }
    return "";
  }

  // ---------- Status rotation ----------

  let statusIntervalId = null;

  function startStatusRotation() {
    const strip = $("certStatusStrip");
    const msg = $("certStatusMessage");
    if (!strip || !msg) return;
    show(strip);
    let idx = 0;
    setText(msg, STATUS_MESSAGES[idx]);
    statusIntervalId = window.setInterval(() => {
      idx = (idx + 1) % STATUS_MESSAGES.length;
      setText(msg, STATUS_MESSAGES[idx]);
    }, STATUS_MESSAGE_HOLD_MS);
  }

  function stopStatusRotation() {
    if (statusIntervalId !== null) {
      window.clearInterval(statusIntervalId);
      statusIntervalId = null;
    }
    hide($("certStatusStrip"));
  }

  // ---------- Rendering ----------

  function renderError(message) {
    const el = $("certError");
    if (!el) return;
    el.textContent = message;
    show(el);
  }

  function renderProfileSummary(text) {
    const el = $("certProfileSummary");
    if (!el || !text) return;
    el.textContent = text;
    show(el);
  }

  function renderResults(results) {
    const container = $("certResults");
    if (!container) return;

    if (!results || results.length === 0) {
      container.innerHTML =
        '<p class="text-muted">No open postings matched today. ' +
        "The federal hiring market shifts daily — try again tomorrow, " +
        "or refine your search above.</p>";
      return;
    }

    container.innerHTML = results.map(renderResultCard).join("");

    // Wire up the "Why this score?" toggles
    container.querySelectorAll(".cert-gaps-toggle").forEach((toggle) => {
      toggle.addEventListener("click", () => {
        const target = toggle.nextElementSibling;
        if (!target) return;
        const isOpen = target.style.display !== "none";
        target.style.display = isOpen ? "none" : "block";
        toggle.textContent = isOpen ? "Why this score?" : "Hide details";
      });
    });
  }

  function renderResultCard(r) {
    const tagClass = escapeHtml(r.eligibility_tag || "");
    const tagLabel = (r.eligibility_note || "").trim() || tagLabelFallback(r.eligibility_tag);
    const scoreClass = r.match_score < 5 ? "weak" : "";

    const gapsHtml =
      r.gaps && r.gaps.length > 0
        ? `<div class="cert-gaps-toggle">Why this score?</div>
           <ul class="cert-gaps" style="display: none;">
             ${r.gaps.map((g) => `<li>${escapeHtml(g)}</li>`).join("")}
           </ul>`
        : "";

    return `
      <div class="cert-result-card">
        <div class="cert-result-header">
          <div style="flex: 1; min-width: 0;">
            <h3 class="cert-result-title">
              <a href="${escapeHtml(r.apply_url)}" target="_blank" rel="noopener noreferrer">
                ${escapeHtml(r.title)}
              </a>
            </h3>
            <div class="cert-result-meta">
              ${escapeHtml(r.agency)} • ${escapeHtml(r.location)} • ${escapeHtml(r.grade)}
              ${r.salary_range ? " • " + escapeHtml(r.salary_range) : ""}
              ${r.closing_date ? " • Closes " + escapeHtml(r.closing_date) : ""}
            </div>
            <span class="cert-eligibility-tag ${tagClass}">${escapeHtml(tagLabel)}</span>
          </div>
          <div class="cert-score-badge ${scoreClass}">${r.match_score}/10</div>
        </div>
        <p class="cert-match-reason">${escapeHtml(r.match_reason)}</p>
        ${gapsHtml}
      </div>
    `;
  }

  function tagLabelFallback(tag) {
    switch (tag) {
      case "open_to_public":
        return "Open to public";
      case "status_qualified":
        return "You qualify under federal status";
      case "veterans_qualified":
        return "You qualify via veteran preference";
      default:
        return "";
    }
  }

  // ---------- Run handler ----------

  function clearPriorRun() {
    hide($("certError"));
    hide($("certProfileSummary"));
    const results = $("certResults");
    if (results) results.innerHTML = "";
  }

  async function onRunClick() {
    const resumeText = getResumeText();
    if (!resumeText) {
      renderError(
        "Paste your resume into the box above first, then click Run Cert."
      );
      return;
    }

    const userPrompt = ($("certPrompt").value || "").trim() || null;

    clearPriorRun();
    const btn = $("certRunBtn");
    btn.disabled = true;
    startStatusRotation();

    try {
      const response = await fetch("/cert/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          user_prompt: userPrompt,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        renderError(data.error || "Something went wrong. Please try again.");
        return;
      }

      const session = data.session_state || {};

      if (session.needs_disambiguation) {
        renderError(
          session.disambiguation_question ||
            "Cert needs more information to search effectively."
        );
        return;
      }

      if (session.profile_summary) {
        renderProfileSummary(session.profile_summary);
      }

      renderResults(data.results || []);
    } catch (err) {
      console.error("Cert run failed:", err);
      renderError(
        "Couldn't reach Cert. Check your network and try again."
      );
    } finally {
      stopStatusRotation();
      btn.disabled = false;
    }
  }

  // ---------- Initialization ----------

  document.addEventListener("DOMContentLoaded", () => {
    const btn = $("certRunBtn");
    if (btn) {
      btn.addEventListener("click", onRunClick);
    }
  });
})();