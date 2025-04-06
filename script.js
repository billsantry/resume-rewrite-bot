async function rewriteResume() {
  const apiKey = document.getElementById("apiKey").value.trim();
  const jobDesc = document.getElementById("jobDesc").value.trim();
  const resume = document.getElementById("resume").value.trim();
  const resultBox = document.getElementById("result");

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
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": \`Bearer \${apiKey}\`
      },
      body: JSON.stringify({
        model: "gpt-3.5-turbo",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.7
      })
    });

    const data = await response.json();

    if (data.choices && data.choices.length > 0) {
      resultBox.textContent = data.choices[0].message.content.trim();
    } else {
      resultBox.textContent = "No response received. Check your API key or input format.";
    }

  } catch (err) {
    console.error(err);
    resultBox.textContent = "Error: Could not reach OpenAI API.";
  }
}
