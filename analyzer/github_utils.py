
import io
import json
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests

MAX_FILE_SIZE = 100_000
MAX_FILES = 40
TIMEOUT = 30

IGNORED_DIRECTORIES = {
    ".git", ".github", ".venv", "venv", "__pycache__",
    "node_modules", "dist", "build", "site-packages",
    "examples", "example", "tests", "test", "docs",
    "documentation", "migrations",
}

IGNORED_FILES = {
    ".env", "package-lock.json", "poetry.lock",
    "Pipfile.lock", "yarn.lock",
}

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
    ".cpp", ".c", ".h", ".cs", ".go", ".rs", ".php",
    ".rb", ".html", ".css", ".sql", ".md", ".txt",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sh", ".bat", ".ps1",
}

PRIORITY_NAMES = {
    "readme.md": 0,
    "pyproject.toml": 1,
    "package.json": 1,
    "requirements.txt": 1,
    "cargo.toml": 1,
    "go.mod": 1,
    "pom.xml": 1,
    "setup.py": 1,
    "main.py": 2,
    "app.py": 2,
    "index.js": 2,
    "index.ts": 2,
}


def parse_github_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url.strip())

    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError(
            "Enter a valid URL, e.g. https://github.com/pallets/flask"
        )

    parts = [p for p in parsed.path.strip("/").split("/") if p]

    if len(parts) < 2:
        raise ValueError("URL must include the repository owner and name.")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")

    if owner in {".", ".."} or repo in {"", ".", ".."}:
        raise ValueError("Could not identify the repository.")

    return owner, repo


def _download_repository(owner: str, repo: str):
    session = requests.Session()
    session.headers.update({"User-Agent": "Local-Repository-Analyzer"})

    # Try the default branch first, then the other common branch.
    errors = []

    for branch in ("main", "master"):
        url = (
            f"https://github.com/{owner}/{repo}/archive/refs/heads/"
            f"{branch}.zip"
        )

        try:
            response = session.get(url, timeout=TIMEOUT)

            if response.status_code == 404:
                continue

            response.raise_for_status()

            archive = zipfile.ZipFile(io.BytesIO(response.content))
            return session, archive

        except (requests.RequestException, zipfile.BadZipFile) as error:
            errors.append(str(error))

    raise ValueError(
        "Could not download this repository. Check the URL and make sure "
        "the repository is public. Its default branch may also be unsupported."
    )


def get_repository_info(repo_url: str) -> dict:
    owner, repo = parse_github_url(repo_url)

    try:
        response = requests.get(
            f"https://github.com/{owner}/{repo}",
            headers={"User-Agent": "Local-Repository-Analyzer"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(f"Could not access the GitHub page: {error}") from error

    # Use the public page's embedded metadata when available.
    from html.parser import HTMLParser

    class MetadataParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.meta = {}

        def handle_starttag(self, tag, attrs):
            if tag != "meta":
                return
            values = dict(attrs)
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.meta[key] = values["content"]

    parser = MetadataParser()
    parser.feed(response.text)
    meta = parser.meta

    description = meta.get("og:description", "").strip()
    title = meta.get("og:title", f"{owner}/{repo}")

    return {
        "name": f"{owner}/{repo}",
        "description": description or "No description available.",
        "url": f"https://github.com/{owner}/{repo}",
        "stars": None,
        "language": "Determine from downloaded files",
        "default_branch": "Detected from downloaded archive",
        "size": None,
    }


def get_repository_files(repo_url: str) -> list[dict]:
    owner, repo = parse_github_url(repo_url)
    session, archive = _download_repository(owner, repo)

    candidates = []

    with archive:
        for name in archive.namelist():
            path = PurePosixPath(name)

            # Skip the ZIP's top-level repository folder.
            parts = path.parts[1:]
            if not parts:
                continue

            filename = parts[-1]
            extension = path.suffix.lower()

            if any(part.lower() in IGNORED_DIRECTORIES for part in parts[:-1]):
                continue

            if filename.lower().startswith(".env"):
                continue

            if filename in IGNORED_FILES or extension not in ALLOWED_EXTENSIONS:
                continue

            try:
                info = archive.getinfo(name)
            except KeyError:
                continue

            if info.file_size > MAX_FILE_SIZE:
                continue

            priority = PRIORITY_NAMES.get(filename.lower(), 3)
            if len(parts) > 1:
                priority += 1

            candidates.append((priority, "/".join(parts), name))

        candidates.sort(key=lambda item: (item[0], item[1]))

        result = []

        for _, path, archive_name in candidates[:MAX_FILES]:
            try:
                content = archive.read(archive_name).decode(
                    "utf-8", errors="replace"
                )
                result.append({"path": path, "content": content})
            except (KeyError, RuntimeError, zipfile.BadZipFile):
                continue

    return result
