# Prompt comparison: `pallets/flask`

Model: `llama3.2:3b` on CPU (Ollama) · Test repository: <https://github.com/pallets/flask> · 32 files downloaded, 25 source files.

This file records how the review prompts changed and why. All outputs below were produced by the app on a real run; excerpts are shortened only where marked `[...]`.

## Summary of the iterations

| Version | Change | Result on Flask |
| --- | --- | --- |
| **v1 (original)** | One prompt, five jobs, up to ~30,000 characters of code | Generic text. The code review gives no quoted code, so none of it can be checked. |
| **v2** | Three focused prompts (summary, code review, documentation). Findings must quote one exact line. A verifier checks the quote. | Summary named real files, but described the wrong project. Code finding was invented. |
| **v3** | Summary uses the README introduction; README checklist computed by code; more verifier checks | Output still wrong: the analyzer had chosen the **wrong README** (see below). |
| **v4** | Fixed the analyzer bug; 2 model calls instead of 3; capped output length; sections shown as they finish | "What it does" correct. "Limits" line wrong. Weak finding still displayed. |
| **v5 (current)** | "Limits" written by code; findings that fail verification are removed and counted; local cache | Correct summary, correct checklist, honest limits, no invented findings. |

## 1. POOR: original prompt (v1)

> **1. Executive Summary**
> This repository is a Flask web application framework, which provides a flexible and modular way to build web applications. The repository contains the core Flask framework, as well as several blueprints and utilities that can be used to build web applications.
>
> **2. Architecture and Key Components**
> `flask`: The core Flask framework [...] `blueprints`: A set of blueprints [...] `cli`: A set of command-line tools [...] `globals`: A set of global variables and functions [...] `helpers`: A set of helper functions [...]
>
> **3. Code Review**
> The code in the repository appears to be well-organized and maintainable. However, there are a few potential issues that were identified:
> - In the `blueprints.py` file, the `get_send_file_max_age` method is called with a filename as an argument. However, the method does not check if the filename is valid before using it. This could potentially lead to errors [...]
> - In the `cli.py` file, the `find_best_app` function [...] does not handle the case where the module does not contain a Flask application. This could potentially lead to errors [...]
> - In the `globals.py` file, the `current_app` variable is used to access the current Flask application. However, the variable is not checked for validity before being used. This could potentially lead to errors [...]
>
> **4. Documentation Review**
> [...] The README file could benefit from more concrete examples of how to use the Flask framework and its various components. [...]
>
> **5. Recommendations**
> 1. Improve the `get_send_file_max_age` method [...] adding a check to ensure that the filename is a string and that it is not empty. [...]

**Problems**

- **Nothing can be verified.** The code review quotes no line of code. Every finding is phrased as "could potentially lead to errors", which is a guess, not a confirmed defect.
- **Components were not chosen by importance.** The AI was shown the first source files in download order, then cut off, so the "key components" are whatever came first.
- **The documentation advice ignores the README.** It asks for "more concrete examples", but Flask's README already contains a *"A Simple Example"* section with code.
- Very slow: about 7 minutes on a CPU in our test.

## 2. Intermediate: focused prompts (v2)

> **What it does:** This repository contains code for an alternative Flask implementation, Sans-IO. [...] It cannot do any IO operations [...]
>
> **Finding 1: Missing error handling in `run_simple`** — File: `src/flask/cli.py` — Evidence: `from werkzeug import run_simple` — Problem: The `run_simple` function from Werkzeug does not handle all possible exceptions [...] potentially leading to silent failures.
>
> **README checklist (written by the AI):** Install steps: No · Usage example: No · Contribution info: No

**What improved:** real file names (`src/flask/app.py`, `cli.py`, `sansio/app.py`), a structured finding with a quoted line.

**What was still wrong**

- "What it does" described only the `sansio` folder as if it were all of Flask.
- The quoted evidence line is not a line that exists in the repository (Flask imports `run_simple` from `werkzeug.serving`), and an import line cannot show a bug anyway.
- The checklist said "Usage example: No", but the README has one.

## 3. Root cause found with the help of the comparison

The wrong summary and the wrong checklist had the **same cause, and it was not the AI**. The analyzer overwrote the README for every file called `README.md`, so the last one found, `src/flask/sansio/README.md`, replaced the main README. The AI was correctly summarizing the wrong document.

**Fix** (`analyzer/repository_analyzer.py`): keep the README closest to the repository root.

## 4. IMPROVED: current version (v5)

> **What it does:** Flask is a lightweight web application framework that makes it easy to build complex web applications. It provides a simple and flexible way to create web applications, and it is designed to scale up to meet the needs of larger applications.
>
> **Tech stack:** Python, WSGI, Werkzeug, Jinja, Click
>
> **Key components:** `src/flask/app.py`, `src/flask/__main__.py`, `src/flask/cli.py`, `src/flask/sansio/app.py`, `src/flask/json/provider.py` (each with a one-line description)
>
> **Limits:** Only 32 files of the repository were downloaded; large repositories are not fully included. The AI read 6 of 25 source files (entry points and files closest to the root first), so it has not seen the whole codebase.
>
> **Code Review:** No verified issues found. The AI's suggestions did not pass the evidence check.
> 🛡️ 1 AI finding removed automatically: could not be verified against the code. Reason: the evidence is only an import line, which does not show a bug.
>
> **README checklist (checked by script, not by the AI):** Project purpose: Yes · Install steps: **Missing** · Usage example: Yes · Contribution info: Yes · License mentioned in README: **Missing** · LICENSE file in repository: Yes
>
> **Suggested improvements:** Add an Installation section with the exact install command and the supported language version. Add a License section naming the license and linking to the LICENSE file.

## Before and after

| Question | v1 (original) | v5 (current) |
| --- | --- | --- |
| Does the summary describe the whole project correctly? | Vaguely | Yes |
| Are the listed key components real files? | Folder and module names, chosen by download order | Real paths |
| Can every code finding be checked? | No, no code is quoted | Yes: each needs a quoted line that exists in the repo |
| What happens to invented or weak findings? | Shown as fact | Removed and counted in the report |
| README checklist matches the real README? | No ("more examples" although one exists) | Yes (computed by code) |
| States what it could not see? | No | Yes, from real numbers |
| Model calls per review | 1 very large call | 2 small calls, capped output, plus cache |

## What we learned

1. **Check the input before blaming the model.** The wrong summary came from a one-line analyzer bug.
2. **Let code answer questions that have exact answers.** The README checklist, the limits and the file-exists check are all deterministic.
3. **A small model needs a small, strict job.** Short prompts, the task last, quoted evidence, and a verifier that is allowed to say "no verified issues".
4. **Honest output beats impressive output.** Reporting "no verified issues" is a feature, not a failure.

## Caveats

- This comparison covers one repository (`pallets/flask`) and one model. Run `python evaluate_prompts.py <url>` to add more repositories to this folder.
- The verifier proves that a quoted line exists; it cannot prove that the described problem is real.