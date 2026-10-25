
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)


def generate_repository_review(report: dict) -> str:
    """Generate an AI summary and code review using local Ollama."""

    source_files = report.get("source_files", [])
    readme = report.get("readme") or "No README was found."
    important_files = report.get("important_files", [])

    code_samples = []
    for file in source_files[:8]:
        code_samples.append(
            f"\n--- FILE: {file['path']} ---\n"
            f"{file.get('content', '')[:4000]}"
        )

    config_samples = []
    for file in important_files[:4]:
        config_samples.append(
            f"\n--- FILE: {file['path']} ---\n"
            f"{file.get('content', '')[:2000]}"
        )

    prompt = f"""
You are an experienced software engineer reviewing a public GitHub repository.

Analyze only the evidence provided. Do not invent files, dependencies,
features, bugs, or test results. If evidence is insufficient, say so.
Distinguish confirmed observations from potential issues.

Repository: {report.get('name', 'Unknown')}
Languages: {report.get('languages', {})}
Files analyzed: {report.get('total_files', 0)}

README:
{readme[:5000]}

Configuration files:
{"".join(config_samples)[:6000]}

Selected source code:
{"".join(code_samples)[:18000]}

Write a useful report with these sections:

## 1. Executive Summary
Explain what the repository does in simple language.

## 2. Architecture and Key Components
Describe the components visible in the provided files.

## 3. Code Review
Identify potential bugs, maintainability problems, or risky patterns.
For every finding, include the file path and explain the evidence.
Do not claim a bug exists unless the provided code supports that conclusion.

## 4. Documentation Review
Explain what the README communicates and suggest concrete improvements.

## 5. Recommendations
Give the three most useful next steps for this project.

Be specific, readable, and honest about the limits of this partial review.
"""

    response = client.chat.completions.create(
        model="llama3.2:3b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful code reviewer. Ground every finding "
                    "in the supplied repository evidence."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content or (
        "The AI model returned an empty response."
    )
