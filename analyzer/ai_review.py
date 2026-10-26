"""AI review for RepoLens AI, powered by a local Ollama model.

The app calls generate_repository_review(). It makes TWO model calls (summary
and code review) using focused prompts from commit/prompts.py. The README
checklist and its improvement suggestions are produced by plain code, which is
instant and cannot contradict itself. Code-review findings are checked against
the real files and flagged when they look invented.
"""

from openai import OpenAI

from commit.prompts import (
    MAX_OUTPUT_TOKENS,
    build_code_review_messages,
    build_summary_messages,
    flag_unverified_findings,
    limits_markdown,
    readme_checklist_markdown,
    readme_improvements_markdown,
)

MODEL = "llama3.2:3b"

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=600,
)


def _ask(messages: list[dict], max_tokens: int, model: str = MODEL) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,  # shorter answers = much faster on a CPU
    )
    return response.choices[0].message.content or (
        "The AI model returned an empty response."
    )


def documentation_section(report: dict) -> str:
    """Instant, code-generated README review (no model call)."""
    return readme_checklist_markdown(report) + "\n\n" + readme_improvements_markdown(report)


def generate_repository_review(report: dict, model: str = MODEL, on_progress=None) -> str:
    """Return one markdown report.

    on_progress(markdown_so_far) is called after every finished section, so the
    app can show results while the next section is still being written.
    """
    parts: list[str] = []

    def publish(title: str, body: str) -> None:
        parts.append(f"# {title}\n\n{body}")
        if on_progress:
            on_progress("\n\n---\n\n".join(parts))

    # Instant section first, so the user sees something right away.
    publish("Documentation Review", documentation_section(report))

    summary = _ask(build_summary_messages(report), MAX_OUTPUT_TOKENS["summary"], model)
    summary = summary.split("## Limits")[0].rstrip()  # limits are written by code
    parts.insert(0, f"# Repository Summary\n\n{summary}\n\n{limits_markdown(report)}")
    if on_progress:
        on_progress("\n\n---\n\n".join(parts))

    code_review = flag_unverified_findings(
        _ask(build_code_review_messages(report), MAX_OUTPUT_TOKENS["code_review"], model),
        report,
        drop_failed=True,  # hide findings whose evidence cannot be verified
    )
    parts.insert(1, f"# Code Review\n\n{code_review}")
    if on_progress:
        on_progress("\n\n---\n\n".join(parts))

    return "\n\n---\n\n".join(parts)


def generate_repository_review_v1(report: dict) -> str:
    """OLD version (prompt v1): one big prompt. Kept only so evaluate_prompts.py
    can show the 'before' result next to the new one."""

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