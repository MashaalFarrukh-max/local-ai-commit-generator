
import pytest

from commit.prompts import (
    PROMPT_BUILDERS,
    PROMPT_VERSION,
    build_code_review_messages,
    build_docs_messages,
    build_summary_messages,
    count_unverified_findings,
    flag_unverified_findings,
    limits_markdown,
    readme_checklist,
    readme_checklist_markdown,
    readme_improvements_markdown,
    readme_intro,
    select_source_files,
)


@pytest.fixture
def report():
    return {
        "name": "demo-project",
        "total_files": 3,
        "languages": {"Python": 2, "Markdown": 1},
        "readme": (
            "# Demo Project\n\n"
            "This project helps developers analyze repositories and review code.\n\n"
            "## Installation\n"
            "Run `pip install demo-project`.\n\n"
            "## Usage\n"
            "```python\nprint('hello')\n```\n\n"
            "## Contributing\nPlease contribute.\n\n"
            "## License\nMIT\n"
        ),
        "file_tree": ["app.py", "utils.py", "LICENSE"],
        "source_files": [
            {"path": "app.py", "content": "print('hello')"},
            {"path": "utils.py", "content": "def add(a, b):\n    return a + b"},
        ],
        "important_files": [
            {"path": "requirements.txt", "content": "requests==2.32.3"}
        ],
    }


def test_prompt_version_exists():
    assert PROMPT_VERSION


def test_prompt_builders_have_three_tasks():
    assert set(PROMPT_BUILDERS) == {"summary", "code_review", "documentation"}


def test_select_source_files_prioritizes_entry_point(report):
    files = select_source_files(report)
    assert files[0]["path"] == "app.py"


def test_select_source_files_skips_test_files():
    report = {
        "source_files": [
            {"path": "tests/test_app.py", "content": "assert True"},
            {"path": "app.py", "content": "print('hello')"},
        ]
    }
    assert [f["path"] for f in select_source_files(report)] == ["app.py"]


def test_select_source_files_skips_empty_files():
    report = {
        "source_files": [
            {"path": "empty.py", "content": "  "},
            {"path": "app.py", "content": "print('hello')"},
        ]
    }
    assert [f["path"] for f in select_source_files(report)] == ["app.py"]


def test_select_source_files_respects_max_files():
    report = {
        "source_files": [
            {"path": f"module{i}.py", "content": "x = 1"}
            for i in range(5)
        ]
    }
    assert len(select_source_files(report, max_files=2)) == 2


def test_readme_intro_skips_heading_and_code():
    readme = "# Title\n\nUseful introduction text here.\n\n```python\nsecret()\n```\n"
    intro = readme_intro(readme)
    assert "Useful introduction text" in intro
    assert "secret()" not in intro


def test_readme_intro_handles_empty_input():
    assert readme_intro("") == ""


def test_readme_intro_respects_character_limit():
    assert len(readme_intro("A" * 100, max_chars=20)) <= 20


def test_readme_checklist_detects_complete_readme(report):
    results = dict(readme_checklist(report))
    assert results["Project purpose explained"] is True
    assert results["Install steps"] is True
    assert results["Usage example"] is True
    assert results["Contribution info"] is True
    assert results["License mentioned in README"] is True
    assert results["LICENSE file in repository"] is True


def test_readme_checklist_detects_missing_readme_items():
    results = dict(readme_checklist({"readme": "", "file_tree": []}))
    assert all(value is False for value in results.values())


def test_readme_checklist_markdown_mentions_script(report):
    output = readme_checklist_markdown(report)
    assert "README checklist" in output
    assert "checked by script" in output


def test_readme_improvements_include_missing_items():
    output = readme_improvements_markdown(
        {"readme": "", "file_tree": []}
    )
    assert "Suggested improvements" in output
    assert "Create a README.md" in output


def test_limits_markdown_reports_file_counts(report):
    output = limits_markdown(report)
    assert "3 files" in output
    assert "2 of 2 source files" in output


def test_summary_prompt_contains_repository_evidence(report):
    messages = build_summary_messages(report)
    assert messages[0]["role"] == "system"
    assert "demo-project" in messages[1]["content"]
    assert "What it does" in messages[1]["content"]


def test_code_review_prompt_requires_exact_evidence(report):
    messages = build_code_review_messages(report)
    assert "Evidence" in messages[1]["content"]
    assert "app.py" in messages[1]["content"]


def test_docs_prompt_includes_checked_readme_list(report):
    messages = build_docs_messages(report)
    assert "CHECKLIST" in messages[1]["content"]
    assert "Install steps" in messages[1]["content"]


def test_verifier_warns_about_invented_evidence(report):
    review = (
        "### Finding 1: Unsafe operation\n"
        "- File: app.py\n"
        "- Evidence: `dangerous_function(user_input)`\n"
        "- Problem: This causes a failure.\n"
        "- Confidence: High"
    )
    output = flag_unverified_findings(review, report)
    assert "not in the repository files" in output


def test_verifier_removes_unverified_finding(report):
    review = (
        "### Finding 1: Unsafe operation\n"
        "- File: app.py\n"
        "- Evidence: `dangerous_function(user_input)`\n"
        "- Problem: This causes a failure.\n"
        "- Confidence: High"
    )
    output = flag_unverified_findings(review, report, drop_failed=True)
    assert "No verified issues found" in output
    assert "finding removed automatically" in output


def test_verifier_keeps_valid_finding_and_counts_warnings(report):
    review = (
        "### Finding 1: Unsafe operation\n"
        "- File: app.py\n"
        "- Evidence: `print('hello')`\n"
        "- Problem: This might fail in some cases.\n"
        "- Confidence: Medium"
    )
    output = flag_unverified_findings(review, report)
    assert "Finding 1" in output
    assert count_unverified_findings(output) >= 1


def test_function_signature_is_not_accepted_as_bug_evidence():
    report = {
        "source_files": [
            {
                "path": "src/example.py",
                "content": (
                    "def to_native_string(string: str) -> str:\n"
                    "    return string\n"
                ),
            }
        ],
        "important_files": [],
        "readme": "",
        "file_tree": ["src/example.py"],
    }

    review = """### Finding 1: Missing error handling
- File: src/example.py
- Evidence: `def to_native_string(string: str) -> str:`
- Problem: This function does not handle invalid input.
- Confidence: Medium
"""

    result = flag_unverified_findings(review, report, drop_failed=True)

    assert "No verified issues found" in result
    assert "function signature" in result
