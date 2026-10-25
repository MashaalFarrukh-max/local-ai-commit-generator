
from analyzer.github_utils import get_repository_files
from analyzer.repository_analyzer import analyze_repository

url = "https://github.com/pallets/flask"

files = get_repository_files(url)
report = analyze_repository(files)

print("\n--- Repository Summary ---")
print("Files analyzed:", report["total_files"])

print("\n--- Languages ---")
for language, count in report["languages"].items():
    print(f"{language}: {count} files")

print("\n--- Important Files ---")
for file in report["important_files"]:
    print(file["path"])

print("\n--- Source Files Available for AI ---")
print("Source files:", len(report["source_files"]))

print("\n--- README ---")
if report["readme"]:
    print(report["readme"][:500])
else:
    print("README was not included in the retrieved files.")
