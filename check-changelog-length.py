import re
import sys
from pathlib import Path

LIMIT = 160
CHANGELOG = Path("docs/changelog.md")

ISSUE_LINK = re.compile(r"\s*\(\[GH-\d+\]\([^)]*\)(?:,\s*\[GH-\d+\]\([^)]*\))*\)")
MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ENTRY = re.compile(r"^\s*- (.*)$")


def payload(entry: str) -> str:
    return MARKDOWN_LINK.sub(r"\1", ISSUE_LINK.sub("", entry)).strip()


def main() -> int:
    lines = CHANGELOG.read_text().splitlines()
    try:
        start = lines.index("## Unreleased") + 1
    except ValueError:
        return 0
    end = next(
        (i for i, line in enumerate(lines[start:], start) if line.startswith("## ")),
        len(lines),
    )

    violations = [
        (i, text)
        for i, line in enumerate(lines[start:end], start + 1)
        if (match := ENTRY.match(line)) and len(text := payload(match.group(1))) > LIMIT
    ]
    for line_number, text in violations:
        print(
            f"{CHANGELOG}:{line_number}: changelog entry has {len(text)} characters, "
            f"limit is {LIMIT}:\n    {text}",
            file=sys.stderr,
        )
    if violations:
        print(
            "\nKeep entries to one sentence stating what changed. "
            "The reasoning belongs in the commit message and the linked issue.",
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
