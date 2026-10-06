"""Check local Markdown/HTML links and keep private runtime files out of Git."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    files = sorted({ROOT / n for n in names if n and (ROOT / n).is_file()})
    problems, checked = [], 0
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(("data/", "output/", "external-materials/", ".venv/")) or path.name in {".env", "qq-auth.bin", "qq-config.json"}:
            problems.append(f"Private runtime path included: {relative}")
        if path.suffix != ".md":
            continue
        body = path.read_text(encoding="utf-8")
        body = re.sub(r"```.*?```", "", body, flags=re.S)
        links = re.findall(r"\]\(([^)]+)\)", body) + re.findall(r'(?:src|href)="([^"]+)"', body)
        for link in links:
            # Standard local paths only; external URLs/anchors are not network-tested.
            link = link.strip().strip("<>")
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path:
                continue
            target = (path.parent / unquote(url.path)).resolve()
            checked += 1
            if not target.is_relative_to(ROOT) or not target.exists():
                problems.append(f"{relative}: broken local link {link}")
    for problem in problems:
        print(problem)
    print(f"Checked {checked} local links across {len(files)} files; {len(problems)} problems")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
