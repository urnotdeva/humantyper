"""QWERTY adjacency typos and typing rhythm helpers."""

from __future__ import annotations

import random

QWERTY_ROWS = [
    "`1234567890-=",
    " qwertyuiop[]\\",
    " asdfghjkl;'",
    " zxcvbnm,./",
]


def _build_adjacency() -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for r, row in enumerate(QWERTY_ROWS):
        for c, ch in enumerate(row):
            if ch == " ":
                continue
            neighbors: list[str] = []
            for dr in (-1, 0, 1):
                nr = r + dr
                if 0 <= nr < len(QWERTY_ROWS):
                    other = QWERTY_ROWS[nr]
                    for dc in (-1, 0, 1):
                        nc = c + dc
                        if (
                            0 <= nc < len(other)
                            and other[nc] != " "
                            and not (dr == 0 and dc == 0)
                        ):
                            neighbors.append(other[nc])
            adj[ch] = neighbors
    return adj


KEY_ADJACENCY = _build_adjacency()

FAST_BIGRAMS = {
    "th",
    "he",
    "in",
    "er",
    "an",
    "re",
    "on",
    "at",
    "en",
    "nd",
    "ti",
    "es",
    "or",
    "te",
    "of",
    "ed",
    "is",
    "it",
    "al",
    "ar",
}

PAUSE_AFTER = set("{};\n")


def typo_for(ch: str) -> str | None:
    """Return a plausible mistaken character for ch, or None."""
    lower = ch.lower()
    neighbors = KEY_ADJACENCY.get(lower)
    if not neighbors:
        return None
    sub = random.choice(neighbors)
    return sub.upper() if ch.isupper() else sub
