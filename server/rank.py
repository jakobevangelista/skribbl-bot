"""The letter board decides which words are possible. The drawing only sorts them.

The vision model names what a bad sketch looks like. It does not spell the
answer. Words come from the Skribbl list, already in easy-to-draw order.
"""

from __future__ import annotations

from pattern import Slot, matches

# Few enough legal words to show the whole set and skip another model call.
TIGHT_LIMIT = 12
# A wide-open board stays a short list, best match to the sketch first.
LOOSE_LIMIT = 12


def _playable(word: str, slots: list[Slot] | None) -> bool:
    """Drop one-letter scraps and spaces the board does not have."""
    if slots is None:
        return len(word) >= 2 and " " not in word
    if len(slots) != 1 and len(word) < 2:
        return False
    board_has_space = any(slot.kind == "gap" or slot.char == " " for slot in slots)
    if " " in word and not board_has_space:
        return False
    return matches(word, slots)


def _clean_list(words: list[str], blocked: set[str]) -> list[str]:
    cleaned_words: list[str] = []
    seen: set[str] = set()
    for word in words:
        cleaned = word.strip().lower()
        if not cleaned or cleaned in blocked or cleaned in seen:
            continue
        seen.add(cleaned)
        cleaned_words.append(cleaned)
    return cleaned_words


def _seeds(words: list[str]) -> list[str]:
    seeds: list[str] = []
    for word in words:
        seeds.append(word)
        seeds.extend(part for part in word.replace("-", " ").split() if len(part) >= 3)
    return seeds


def _score(word: str, seeds: list[str]) -> int:
    """How much a legal answer resembles what the sketch was called."""
    best = 0
    parts = [part for part in word.replace("-", " ").split() if part]
    for seed in seeds:
        if seed == word:
            best = max(best, 100)
            continue
        if seed in parts:
            best = max(best, 70)
            continue
        if len(seed) < 4:
            continue
        if any(seed in part or part in seed for part in parts):
            best = max(best, 40 + min(len(seed), 12))
        elif seed in word or word in seed:
            best = max(best, 25)
    return best


def matching_words(
    slots: list[Slot] | None,
    dictionary: list[str],
    rejects: list[str],
) -> list[str]:
    """Every dictionary word the current board allows, in list order."""
    if slots is None:
        return []
    blocked = {word.strip().lower() for word in rejects}
    return [word for word in _clean_list(dictionary, blocked) if _playable(word, slots)]


def rank(
    raw: list[str],
    slots: list[Slot] | None,
    dictionary: list[str],
    rejects: list[str],
) -> tuple[list[str], list[str], list[str]]:
    blocked = {word.strip().lower() for word in rejects}
    described = _clean_list(raw, blocked)
    if slots is None:
        return [word for word in described if _playable(word, None)], [], []

    legal = matching_words(slots, dictionary, rejects)
    seeds = _seeds(described)
    from_sketch = [word for word in described if _playable(word, slots) and word not in set(legal)]
    ordered = sorted(from_sketch + legal, key=lambda word: _score(word, seeds), reverse=True)
    cap = len(ordered) if len(legal) <= TIGHT_LIMIT else LOOSE_LIMIT
    return ordered[:cap], [], []
