"""
Lightweight text similarity for matching questions and schema names.
No external models: fast, deterministic and good enough to rank a few
hundred past questions or a few hundred tables.
"""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an the and or but of to in on at for with by from as is are was were be been being do does did
    have has had i me my we our you your it its this that these those there here what which who whom whose
    when where why how all any each every some show me list give get find tell display please can could
    would should will just than then also into per vs versus""".split()
)

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*|\d+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "ches", "shes", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str | None) -> list[str]:
    """Lower-cased, singularized content words. Splits snake_case and camelCase."""
    if not text:
        return []
    words: list[str] = []
    for raw in _WORD.findall(_CAMEL.sub(" ", text.replace("_", " "))):
        word = raw.lower()
        if word in STOPWORDS:
            continue
        words.append(singular(word))
    return words


def normalize_question(text: str) -> str:
    return " ".join((text or "").lower().split()).rstrip("?.! ")


def similarity(a: str | list[str], b: str | list[str]) -> float:
    """Jaccard similarity of content-word sets, in [0, 1]."""
    ta = set(tokenize(a) if isinstance(a, str) else a)
    tb = set(tokenize(b) if isinstance(b, str) else b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
