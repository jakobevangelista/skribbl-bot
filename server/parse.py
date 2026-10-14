"""Pull a short word list out of a vision-model reply."""

from __future__ import annotations

import re

_MARKER = re.compile(r"^(?:[\-\*\u2022]+|\d+[\.\)\:])\s*")
_ANSWER = re.compile(r"[a-z0-9](?:[a-z0-9 '\-]*[a-z0-9])?", re.IGNORECASE)


def parse_candidates(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = _MARKER.sub("", line).strip().strip("`\"'")
        line = re.split(r"\s+[—–\-]\s+", line, maxsplit=1)[0].strip().lower()
        line = re.sub(r"\s+", " ", line)
        if not line or len(line) > 40 or len(line.split(" ")) > 4:
            continue
        if _ANSWER.fullmatch(line) is None:
            continue
        if line in seen:
            continue
        seen.add(line)
        found.append(line)
    return found
