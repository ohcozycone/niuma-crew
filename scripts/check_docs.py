"""Check local Markdown destinations, headings and the docs navigation graph offline."""

import argparse
import html
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

IGNORED = {
    ".git",
    ".venv",
    ".impeccable",
    ".generated",
    ".source",
    ".next",
    "node_modules",
    "dist",
    "out",
    "__pycache__",
    ".pytest_cache",
}
LINK = re.compile(r'!?\[(?:[^\]\\]|\\.)*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\s*\)')
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)", re.MULTILINE)


def markdown_files(root):
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in IGNORED)
        for name in sorted(files):
            if name.endswith(".md"):
                yield Path(current) / name


def prose(text):
    """Ignore examples inside fences, comments and code spans without hiding real links."""
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            lines.append("")
        else:
            lines.append(line if fence is None else "")
    return re.sub(r"<!--[\s\S]*?-->", "", "\n".join(lines))


def heading_id(title):
    title = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", title)
    title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip().lower()
    title = re.sub(r"\s+#+\s*$", "", title)
    # GitHub keeps Unicode letters/numbers, underscores and hyphens in heading IDs.
    title = "".join(
        char
        for char in title
        if char in "_- " or char.isspace() or unicodedata.category(char)[0] in {"L", "N", "M"}
    )
    return re.sub(r"\s", "-", title)


def heading_ids(text):
    content = prose(text)
    used = set()
    for match in re.finditer(r"^\s{0,3}#{1,6}\s+(.+)$", content, re.MULTILINE):
        base = heading_id(match.group(1))
        value = base
        number = 0
        while value in used:
            number += 1
            value = f"{base}-{number}"
        used.add(value)
    for match in re.finditer(r'\b(?:id|name)=["\']([^"\']+)["\']', content):
        used.add(match.group(1))
    return used


def destinations(text):
    content = re.sub(r"(`+)([^`]|(?!\1)`)*?\1", "", prose(text))
    for pattern in (LINK, REFERENCE):
        for match in pattern.finditer(content):
            yield match.group(1).strip("<>")


def check(root, check_archive=False):
    root = root.resolve()
    files = list(markdown_files(root))
    known = set(files)
    anchors = {path: heading_ids(path.read_text()) for path in files}
    graph = {path: set() for path in files}
    errors = []
    total = archives = 0
    for source in files:
        for value in destinations(source.read_text()):
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc:
                continue
            total += 1
            path = unquote(parsed.path)
            target = (source.parent / path).resolve() if path else source
            try:
                target.relative_to(root)
            except ValueError:
                if target.is_relative_to(root.parent / "niuma-crew-archive"):
                    archives += 1
                    if check_archive and not target.exists():
                        errors.append(f"{source.relative_to(root)}: missing archive {value}")
                    continue
                errors.append(f"{source.relative_to(root)}: path outside project {value}")
                continue
            if not target.exists():
                errors.append(f"{source.relative_to(root)}: missing {value}")
                continue
            if target in known:
                graph[source].add(target)
                fragment = unquote(parsed.fragment)
                if fragment and fragment not in anchors[target]:
                    errors.append(f"{source.relative_to(root)}: missing heading {value}")
    start = root / "docs/README.md"
    if start not in known:
        errors.append("missing docs/README.md")
    else:
        reachable = set()
        pending = [start]
        while pending:
            path = pending.pop()
            if path not in reachable:
                reachable.add(path)
                pending.extend(graph[path] - reachable)
        for path in files:
            if path.is_relative_to(root / "docs") and path not in reachable:
                errors.append(f"{path.relative_to(root)}: unreachable from docs/README.md")
    return errors, {
        "files": len(files),
        "local_links": total,
        "archive_links": archives,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-archive", action="store_true")
    args = parser.parse_args()
    errors, counts = check(Path(__file__).resolve().parents[1], args.check_archive)
    for error in errors:
        print(error)
    print(f"Documentation: {counts}; errors={len(errors)}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
