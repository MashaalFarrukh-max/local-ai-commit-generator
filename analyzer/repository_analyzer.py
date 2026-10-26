from collections import Counter
from pathlib import PurePosixPath


def analyze_repository(files: list[dict]) -> dict:
    """Summarize the languages, structure, and documentation in a repository."""

    if not files:
        return {
            "total_files": 0,
            "languages": {},
            "readme": None,
            "important_files": [],
            "file_tree": [],
            "source_files": [],
        }

    extensions = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".ts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".go": "Go",
        ".rs": "Rust",
        ".php": "PHP",
        ".rb": "Ruby",
        ".html": "HTML",
        ".css": "CSS",
        ".sql": "SQL",
        ".sh": "Shell",
    }

    language_counts = Counter()
    file_tree = []
    important_files = []
    source_files = []
    readme = None
    readme_depth = None  # folder depth of the README chosen so far

    for file in files:
        path = file["path"]
        content = file.get("content", "")
        pure_path = PurePosixPath(path)
        filename = pure_path.name
        extension = pure_path.suffix.lower()

        if extension in extensions:
            language_counts[extensions[extension]] += 1

        file_tree.append(path)

        # Use the README closest to the repository root. Without this, a README
        # in a sub-folder (e.g. src/flask/sansio/README.md) replaced the main one.
        if filename.lower() == "readme.md":
            depth = len(pure_path.parts)
            if readme_depth is None or depth < readme_depth:
                readme = content
                readme_depth = depth

        if filename in {
            "pyproject.toml",
            "requirements.txt",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "pom.xml",
        }:
            important_files.append({
                "path": path,
                "content": content,
            })

        if extension in extensions and content.strip():
            source_files.append({
                "path": path,
                "content": content,
            })

    return {
        "total_files": len(files),
        "languages": dict(language_counts.most_common()),
        "readme": readme,
        "important_files": important_files,
        "file_tree": file_tree,
        "source_files": source_files,
    }