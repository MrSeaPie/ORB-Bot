"""
Run before every commit: fails if any value from .env (the Alpaca keys) appears in the staged
git changes. Never prints the values. The GitHub repo is public, so this matters.

    git add <files>
    .venv\\Scripts\\python.exe tests\\check_no_secrets.py     # exit code 0 = safe to commit
"""
import subprocess
import sys
from pathlib import Path

project = Path(__file__).resolve().parent.parent

secrets = []
for line in (project / ".env").read_text(encoding="utf-8-sig").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        value = line.split("=", 1)[1].strip().strip('"').strip("'")
        if len(value) >= 8:
            secrets.append(value.encode())

diff = subprocess.run(["git", "diff", "--cached", "--text"], capture_output=True, check=True,
                      cwd=project).stdout
leaks = sum(diff.count(s) for s in secrets)
print(f"checked {len(secrets)} secrets against {len(diff):,} bytes of staged changes: {leaks} matches")
sys.exit(1 if leaks else 0)
