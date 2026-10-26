"""Reusable, evidence-grounded prompts for RepoLens AI.

Why this file exists
--------------------
The original review prompt asked a small local model (llama3.2:3b) to do five
jobs at once on ~30,000 characters of code. Two things go wrong with that:

1. Ollama's default context window is small (4096 tokens). Anything beyond it
   is silently cut off from the START of the prompt, which is where the
   instructions live. The model then answers without its rules and invents
   things.
2. Small models invent bugs when they are asked to "find problems" without a
   strict format.

What these prompts do differently
---------------------------------
* One prompt per job (summary, code review, documentation review).
* A character budget so the whole prompt fits the context window.
* The task and rules come LAST, so they survive if anything is truncated.
* Code review findings must quote an exact line from the code. Afterwards,
  ``flag_unverified_findings`` checks that quote against the real files and
  warns about findings whose evidence does not exist.

Usage (inside analyzer/ai_review.py)::

    from commit.prompts import build_code_review_messages, flag_unverified_findings

    messages = build_code_review_messages(report)
    response = client.chat.completions.create(model=MODEL, messages=messages,
                                              temperature=0.2)
    text = response.choices[0].message.content or ""
    text = flag_unverified_findings(text, report)

``report`` is the dict returned by ``analyze_repository`` plus a ``"name"`` key.
"""

import re
from pathlib import PurePosixPath

# v1 = the single large inline prompt that used to live in analyzer/ai_review.py
PROMPT_VERSION = "5"

# Total characters of repository evidence placed in one prompt. 9000 chars is
# roughly 2,300 tokens, which leaves room for instructions and the answer in a
# 4096-token window. If you raise the model's context (see README notes), you
# can pass a larger max_context_chars.
DEFAULT_CONTEXT_CHARS = 6500

# Hard limits on how many tokens the model may WRITE per prompt. Local models
# on a CPU generate only a few tokens per second, so a shorter answer is the
# biggest speed-up. These are used by analyzer/ai_review.py.
MAX_OUTPUT_TOKENS = {"summary": 380, "code_review": 380, "documentation": 250}

SYSTEM_PROMPT = (
    "You are a careful senior software engineer reviewing a GitHub repository "
    "from a partial snapshot. You only know what is shown in the message. "
    "Never invent files, functions, dependencies, bugs or test results. "
    "If something is not in the evidence, say 'Not shown in the provided files'. "
    "Be specific and short."
)

ENTRY_POINTS = {
    "main.py", "app.py", "manage.py", "__main__.py", "cli.py",
    "index.js", "server.js", "app.js", "main.js", "index.ts", "main.ts",
    "main.go", "main.rs", "main.c", "main.cpp", "index.html",
}


# --------------------------------------------------------------------------
# Evidence helpers
# --------------------------------------------------------------------------

def _is_test_file(path: str) -> bool:
    parts = [p.lower() for p in PurePosixPath(path).parts]
    name = parts[-1]
    return (
        any(p in {"test", "tests", "__tests__", "spec"} for p in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    )


def select_source_files(report: dict, max_files: int = 6) -> list[dict]:
    """Pick the most informative source files: entry points first, then
    files closest to the repository root. Test files are skipped."""
    candidates = [
        f for f in report.get("source_files", [])
        if not _is_test_file(f["path"]) and f.get("content", "").strip()
    ]

    def rank(f: dict):
        p = PurePosixPath(f["path"])
        return (p.name.lower() not in ENTRY_POINTS, len(p.parts), f["path"])

    return sorted(candidates, key=rank)[:max_files]


def _pack_files(files: list[dict], budget: int, per_file: int):
    """Fit as many files as possible inside ``budget`` characters.
    Returns (text, list_of_paths_included)."""
    parts, included, used = [], [], 0
    for f in files:
        room = min(per_file, budget - used)
        if room < 300:
            break
        block = f"--- FILE: {f['path']} ---\n{f.get('content', '')[:room].rstrip()}\n\n"
        parts.append(block)
        included.append(f["path"])
        used += len(block)
    return "".join(parts), included


def _overview(report: dict) -> str:
    languages = ", ".join(
        f"{name} ({count})" for name, count in report.get("languages", {}).items()
    ) or "unknown"
    tree = report.get("file_tree", [])
    shown = "\n".join(tree[:40])
    more = f"\n... and {len(tree) - 40} more files" if len(tree) > 40 else ""
    return (
        f"Repository: {report.get('name', 'Unknown')}\n"
        f"Total files: {report.get('total_files', 0)}\n"
        f"Languages (file counts): {languages}\n\n"
        f"File list:\n{shown}{more}\n"
    )


def _config_text(report: dict, budget: int) -> str:
    text, _ = _pack_files(report.get("important_files", [])[:3], budget, per_file=1200)
    return text


def _messages(evidence: str, task: str) -> list[dict]:
    # Evidence first, task LAST: if the context window overflows, the oldest
    # text is dropped, so the instructions must be the newest text.
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{evidence}\n\n=== YOUR TASK ===\n{task}"},
    ]


# --------------------------------------------------------------------------
# Facts that code can check better than a small model
# --------------------------------------------------------------------------

def readme_intro(readme: str, max_chars: int = 700) -> str:
    """First real paragraph(s) of a README: skips titles, badges, HTML and code."""
    paragraphs, current, in_code = [], [], False
    for line in (readme or "").splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not s or s.startswith(("#", "![", "[![", "<", "|", "---", "===")):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            if sum(len(p) for p in paragraphs) >= max_chars:
                break
            continue
        current.append(s)
    if current:
        paragraphs.append(" ".join(current))
    return " ".join(paragraphs)[:max_chars].strip()


_INSTALL_RE = re.compile(
    r"(?im)(\b(pip3?|pipx|conda|npm|yarn|pnpm|cargo|go get|brew|apt(-get)?)\s+install\b"
    r"|^#+\s*(install|installation|setup|getting started)\b)"
)
_USAGE_HEADING_RE = re.compile(r"(?im)^#+\s*(usage|example|examples|quick ?start|getting started|a simple example)")
_LICENSE_RE = re.compile(r"(?i)\blicen[sc]e\b")


def readme_checklist(report: dict) -> list[tuple[str, bool]]:
    """Checks the README with plain code, because a 3B model often gets
    simple yes/no questions about a document wrong."""
    readme = report.get("readme") or ""
    names = {PurePosixPath(p).name.lower() for p in report.get("file_tree", [])}
    has_code = "```" in readme or re.search(r"(?m)^(?: {4}|\t)\S", readme) is not None
    return [
        ("Project purpose explained", len(readme_intro(readme)) >= 60),
        ("Install steps", bool(_INSTALL_RE.search(readme))),
        ("Usage example", has_code or bool(_USAGE_HEADING_RE.search(readme))),
        ("Contribution info", "contribut" in readme.lower()
            or any(n.startswith("contributing") for n in names)),
        ("License mentioned in README", bool(_LICENSE_RE.search(readme))),
        ("LICENSE file in repository",
            any(n.startswith(("license", "licence", "copying")) for n in names)),
    ]


def readme_checklist_markdown(report: dict) -> str:
    lines = ["## README checklist (checked by script, not by the AI)"]
    if not report.get("readme"):
        lines.append("- No README was found in the downloaded files.")
    for label, ok in readme_checklist(report):
        lines.append(f"- {label}: {'Yes' if ok else 'Missing'}")
    return "\n".join(lines)


_IMPROVEMENT_TEXT = {
    "Project purpose explained": "Start the README with a 2-3 sentence description of what the project does and who it is for.",
    "Install steps": "Add an Installation section with the exact install command (for example `pip install ...`) and the supported language version.",
    "Usage example": "Add a Quick start / Usage section with a short code example and its expected output.",
    "Contribution info": "Add a Contributing section (or a CONTRIBUTING file) explaining how to report issues and open pull requests.",
    "License mentioned in README": "Add a License section naming the license and linking to the LICENSE file.",
    "LICENSE file in repository": "Add a LICENSE file so others know they may use and modify the code.",
}


def readme_improvements_markdown(report: dict) -> str:
    """Documentation advice generated from the checklist. Fast, and it cannot
    contradict the checklist the way a small model sometimes does."""
    missing = [label for label, ok in readme_checklist(report) if not ok]
    lines = ["## Suggested improvements"]
    if not report.get("readme"):
        lines.append("- Create a README.md: this repository has none in the downloaded files.")
    for label in missing[:4]:
        lines.append(f"- {_IMPROVEMENT_TEXT[label]}")
    if len(lines) == 1:
        lines.append("- The README covers all the basics. Consider adding screenshots, "
                     "a table of contents, or badges for build status.")
    return "\n".join(lines)


def limits_markdown(report: dict, files_shown: int = 6) -> str:
    """What this review could and could not see, stated as facts by code."""
    total = report.get("total_files", 0)
    sources = len(report.get("source_files", []))
    shown = min(files_shown, sources)
    return (
        "## Limits\n"
        f"- Only {total} files of the repository were downloaded; large repositories "
        "are not fully included.\n"
        f"- The AI read {shown} of {sources} source files (entry points and files "
        "closest to the root first), so it has not seen the whole codebase."
    )


# --------------------------------------------------------------------------
# Prompt 1: repository summary
# --------------------------------------------------------------------------

SUMMARY_TASK = """Explain this repository to a developer who has never seen it.
Use ONLY the files shown above.

Write exactly these three sections and nothing else (no "Limits" section):

## What it does
2-4 plain sentences about the project's purpose. Base this on the README INTRO
when there is one. Never describe one internal folder or module as if it were
the whole project.

## Tech stack
Bullets. Only technologies visible in file extensions, config files or imports.

## Key components
At most 5 bullets in the form: `path/to/file` - what that file does.
Only list files that appear above.

Rules: do not guess features that are not in the code or README. If the purpose
is unclear, say so instead of guessing."""


def build_summary_messages(report: dict, max_context_chars: int = DEFAULT_CONTEXT_CHARS):
    budget = max_context_chars
    readme = (report.get("readme") or "No README was found.")[: budget // 4]
    config = _config_text(report, budget // 6)
    code, included = _pack_files(
        select_source_files(report, max_files=6),
        budget - len(readme) - len(config) - 1500,
        per_file=1800,
    )
    intro = readme_intro(report.get("readme") or "") or "No README intro available."
    evidence = (
        f"{_overview(report)}\n"
        f"README INTRO (the project's own description; trust this first):\n{intro}\n\n"
        f"README:\n{readme}\n\n"
        f"CONFIG FILES:\n{config or 'None found.'}\n"
        f"SOURCE FILES SHOWN ({len(included)} of "
        f"{len(report.get('source_files', []))}):\n{code}"
    )
    return _messages(evidence, SUMMARY_TASK)


# --------------------------------------------------------------------------
# Prompt 2: code review
# --------------------------------------------------------------------------

CODE_REVIEW_TASK = """Review the source files shown above for real problems that are
visible in the code: bugs, missing error handling, hard-coded secrets, unsafe
handling of input, or duplicated / confusing logic.

Report AT MOST 3 findings, most important first. Use exactly this format:

### Finding 1: <short title>
- File: <a file path shown above>
- Evidence: `<ONE line copied exactly from that file>`
- Problem: <one or two sentences: the exact situation in which this line goes wrong>
- Confidence: High | Medium

Strict rules:
- Only report a finding if you can copy an exact line of code as Evidence.
- The Evidence line must itself show the problem. An import line is NOT evidence.
- In Problem, describe a concrete failure. Do not use the words "may", "might",
  "could potentially" or "possibly". If you can only guess, report nothing.
- Do not mention any file that is not shown above.
- Do NOT report: missing tests, missing documentation, missing type hints,
  code style, naming, or performance guesses.
- Do not say a bug exists unless the shown code proves it. Use Confidence
  Low or Medium when you are unsure.
- If you find nothing clear, write exactly: No clear issues found in the provided files."""


def build_code_review_messages(report: dict, max_context_chars: int = DEFAULT_CONTEXT_CHARS):
    code, included = _pack_files(
        select_source_files(report, max_files=6),
        max_context_chars - 1500,
        per_file=2500,
    )
    evidence = (
        f"Repository: {report.get('name', 'Unknown')}\n"
        f"Languages: {', '.join(report.get('languages', {})) or 'unknown'}\n"
        f"Files shown below: {', '.join(included) or 'none'}\n\n"
        f"SOURCE FILES:\n{code or 'No source files available.'}"
    )
    return _messages(evidence, CODE_REVIEW_TASK)


# --------------------------------------------------------------------------
# Prompt 3: documentation review
# --------------------------------------------------------------------------

DOCS_TASK = """The CHECKLIST above was already checked by a script and is correct. Do
not re-check it and never contradict it.

Write exactly these sections:

## Strengths
At most 2 bullets about what the README does well (use the checklist and README).

## Improvements
Exactly 3 concrete improvements. Each must say what to add and where, for
example: "Add a Quick start section with the install command and one example".
Only suggest adding things the checklist marks "Missing". If fewer than 3 items
are missing, suggest clearer wording or better examples for what exists.

Rules: if the README says "No README was found.", say so and suggest the 3 most
important sections to write. Only suggest commands that match the config files
shown above (for example requirements.txt means pip). Do not invent features."""


def build_docs_messages(report: dict, max_context_chars: int = DEFAULT_CONTEXT_CHARS):
    readme = (report.get("readme") or "No README was found.")[: max_context_chars - 3000]
    config = _config_text(report, 1500)
    evidence = (
        f"Repository: {report.get('name', 'Unknown')}\n"
        f"Languages: {', '.join(report.get('languages', {})) or 'unknown'}\n\n"
        f"CHECKLIST (verified by script):\n{readme_checklist_markdown(report)}\n\n"
        f"README:\n{readme}\n\n"
        f"CONFIG FILES:\n{config or 'None found.'}"
    )
    return _messages(evidence, DOCS_TASK)


PROMPT_BUILDERS = {
    "summary": build_summary_messages,
    "code_review": build_code_review_messages,
    "documentation": build_docs_messages,
}


# --------------------------------------------------------------------------
# Output check: catch invented evidence
# --------------------------------------------------------------------------

_EVIDENCE_RE = re.compile(r"^\s*[-*]?\s*Evidence:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _corpus(report: dict) -> str:
    pieces = [f.get("content", "") for f in report.get("source_files", [])]
    pieces += [f.get("content", "") for f in report.get("important_files", [])]
    pieces.append(report.get("readme") or "")
    return _norm("\n".join(pieces))


# Small models vary the heading: "### Finding 1", "## Finding 1", "**Finding 1:**", ...
_FINDING_START_RE = re.compile(r"\s*(?:#{1,6}\s*|\*\*)?Finding\s+\d+", re.IGNORECASE)
_FINDING_SPLIT_RE = re.compile(r"(?im)^(?=\s*(?:#{1,6}\s*|\*\*)?Finding\s+\d+)")
_FILE_RE = re.compile(r"^\s*[-*]?\s*File:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_TITLE_RE = re.compile(r"(?im)^\s*(?:#{1,6}\s*|\*\*)?Finding\s+\d+\s*[:.\-]?\s*(.*)$")
# Topics the code-review prompt forbids; small models still report them.
_OFF_TOPIC_RE = re.compile(
    r"\b(type hints?|type annotations?|docstrings?|documentation|unit tests?|"
    r"test coverage|naming|code style|formatting|unused (import|variable))\b",
    re.IGNORECASE,
)
_PROBLEM_RE = re.compile(r"^\s*[-*]?\s*Problem:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_HEDGE_RE = re.compile(r"\b(may|might|could potentially|potentially|possibly)\b", re.IGNORECASE)
_IMPORT_RE = re.compile(r"^(import\s+\S|from\s+\S+\s+import\s)")



def _check_finding(block: str, corpus: str, known_paths: set) -> tuple[list, list]:
    """Return (hard_problems, soft_problems) for one finding.

    Hard = the finding cannot be trusted.
    Soft = worded like a guess.
    """
    hard, soft = [], []

    match = _EVIDENCE_RE.search(block)
    quote = _norm(match.group(1)).strip("` ") if match else ""

    if not quote:
        hard.append("no evidence line was given")
    else:
        if len(quote) >= 6 and quote not in corpus:
            hard.append(
                "the evidence line is not in the repository files (invented)"
            )

        if _IMPORT_RE.match(quote):
            hard.append(
                "the evidence is only an import line, which does not show a bug"
            )

        # Reject evidence that consists only of a function signature.
        if re.match(
            r"^(async\s+)?def\s+\w+\s*\(.*\)\s*(?:->\s*[^:]+)?\s*:$",
            quote,
        ):
            hard.append(
                "the evidence is only a function signature, "
                "which does not demonstrate a bug"
            )

    file_match = _FILE_RE.search(block)
    cited = (
        file_match.group(1).strip().strip("`* ").lower()
        if file_match
        else ""
    )

    if known_paths and cited and cited not in known_paths:
        hard.append(f"the file `{cited}` does not exist in this repository")

    title = _TITLE_RE.search(block)
    if title and _OFF_TOPIC_RE.search(title.group(1)):
        hard.append("it is a style/documentation remark, not a bug")

    problem = _PROBLEM_RE.search(block)
    if problem and _HEDGE_RE.search(problem.group(1)):
        soft.append("the problem is described as a guess, not a confirmed failure")

    return hard, soft



def flag_unverified_findings(review: str, report: dict, drop_failed: bool = False) -> str:
    """Check every code-review finding against the real repository files.

    drop_failed=False (default): keep all findings and add a warning line to
        each one that looks unreliable.
    drop_failed=True: remove findings that fail a hard check (invented evidence,
        file that does not exist, import-only evidence, style remark, no evidence)
        and add one note saying how many were removed and why. Findings that are
        only worded like a guess are kept, with a warning."""
    corpus = _corpus(report)
    known_paths = {p.lower() for p in report.get("file_tree", [])}
    known_paths |= {f["path"].lower() for f in report.get("source_files", [])}
    out, removed_reasons = [], []
    found_any = kept_any = False
    for block in re.split(_FINDING_SPLIT_RE, review):
        if _FINDING_START_RE.match(block):
            found_any = True
            hard, soft = _check_finding(block, corpus, known_paths)
            if hard and drop_failed:
                removed_reasons.append(hard[0])
                continue
            kept_any = True
            warnings = [w[0].upper() + w[1:] + "." for w in hard + soft]
            if warnings:
                block = block.rstrip() + "".join(f"\n- ⚠️ {w}" for w in warnings) + "\n\n"
        out.append(block)
    result = "".join(out).strip()
    if drop_failed and removed_reasons:
        n = len(removed_reasons)
        why = "; ".join(sorted(set(r.replace(" (invented)", "") for r in removed_reasons)))
        result += (
            f"\n\n> 🛡️ {n} AI finding{'s' if n != 1 else ''} removed automatically: "
            f"could not be verified against the code. Reason: {why}."
        )
    if found_any and not kept_any and drop_failed:
        result = ("No verified issues found. The AI's suggestions did not pass the "
                  "evidence check.\n\n") + result
    if not found_any and "no clear issues" not in review.lower():
        result += ("\n\n- ⚠️ The model did not use the expected finding format, so its "
                   "claims could not be checked against the code.")
    return result + "\n"


def count_unverified_findings(review: str) -> int:
    """How many findings flag_unverified_findings marked (for the test log)."""
    return review.count("- ⚠️") + review.count("🛡️")