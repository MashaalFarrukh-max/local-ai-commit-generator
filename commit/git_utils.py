
import subprocess


def is_git_repo():
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def get_diff(mode="both", max_chars=12000):
    if not is_git_repo():
        raise RuntimeError("Not inside a Git repository.")

    if mode == "staged":
        command = ["git", "diff", "--cached"]
    elif mode == "unstaged":
        command = ["git", "diff"]
    elif mode == "both":
        command = ["git", "diff", "HEAD"]
    else:
        raise ValueError("Mode must be staged, unstaged, or both.")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not read Git diff.")

    diff = result.stdout.strip()

    if not diff:
        return ""

    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n\n[Diff truncated]"

    return diff
