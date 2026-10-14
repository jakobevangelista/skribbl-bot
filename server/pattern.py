"""Turn a Skribbl hint into slots and test candidate answers against them.

Skribbl builds one `.hint` element per character, including the gap between
words. A separate `.word-length` label looks like "3 5". Underscores are
unknown letters. A still-hidden gap is a separator, which is a space or a
hyphen. Hidden-word mode is three question marks and no length label, so
the pattern does not constrain the answer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    kind: str  # "any", "char", or "gap"
    char: str = ""


def slots_from_hints(hints: list[str], word_length: str | None = None) -> list[Slot] | None:
    """Return None when the round is hidden-word mode and length is unknown."""
    if hints and all(hint == "?" for hint in hints) and not (word_length or "").strip():
        return None

    slots: list[Slot] = []
    for hint in hints:
        if hint in ("_", "?"):
            slots.append(Slot("any"))
        elif hint.strip() == "":
            slots.append(Slot("char", " "))
        else:
            slots.append(Slot("char", hint.lower()))

    parts = _length_parts(word_length or "")
    if parts and sum(parts) + len(parts) - 1 == len(slots):
        index = 0
        for part_index, size in enumerate(parts):
            index += size
            if part_index < len(parts) - 1:
                if slots[index].kind == "any":
                    slots[index] = Slot("gap")
                index += 1
    return slots


def _length_parts(word_length: str) -> list[int]:
    parts: list[int] = []
    for token in word_length.split():
        if token.isdigit():
            parts.append(int(token))
    return parts


def matches(word: str, slots: list[Slot] | None) -> bool:
    if slots is None:
        return bool(word.strip())
    text = word.strip().lower()
    if len(text) != len(slots):
        return False
    for char, slot in zip(text, slots):
        if slot.kind == "any":
            if not char.isalnum():
                return False
        elif slot.kind == "gap":
            if char not in (" ", "-"):
                return False
        elif char != slot.char:
            return False
    return True


def unknown_count(slots: list[Slot] | None) -> int:
    if slots is None:
        return 99
    return sum(1 for slot in slots if slot.kind == "any")


def pattern_text(slots: list[Slot] | None) -> str:
    if slots is None:
        return "hidden"
    characters: list[str] = []
    for slot in slots:
        if slot.kind == "any":
            characters.append("_")
        elif slot.kind == "gap":
            characters.append(" ")
        else:
            characters.append(slot.char)
    return "".join(characters)
