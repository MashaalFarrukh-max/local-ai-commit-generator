
from analyzer.github_utils import (
    parse_github_url,
    get_repository_info,
    get_repository_files,
)

url = "https://github.com/pallets/flask"

print("\n--- Testing URL parsing ---")
owner, repo = parse_github_url(url)
print("Owner:", owner)
print("Repository:", repo)

print("\n--- Testing repository information ---")
info = get_repository_info(url)
print(info)

print("\n--- Testing repository files ---")
files = get_repository_files(url)
print("Files retrieved:", len(files))

for file in files[:5]:
    print("\nFile:", file["path"])
    print(file["content"][:150])
