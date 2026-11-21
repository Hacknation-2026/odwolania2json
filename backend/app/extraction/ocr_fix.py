"""Restores Polish diacritics that OCR drops or confuses ("Odwotujacy" -> "Odwołujący").

OCR of scans keeps the shape of a word but often loses the diacritic mark: ł -> l/t/i,
ą -> a/q, ż -> z/ž, ę -> e, ń -> n. A word that is not in the lexicon
(config/lexicon/*.txt, built from correctly spelled documents) is replaced by the most frequent
lexicon word with the same "skeleton" (letters without diacritics), trying the typical OCR
confusions. Words already in the lexicon and words without a lexicon match stay unchanged.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from functools import lru_cache

from app.config import get_settings

WORD = re.compile(r"[^\W\d_]{3,}")
# OCR misreads of ł / ą that are not just a missing mark
CONFUSIONS = {"t": "ł", "i": "ł", "q": "ą"}
MAX_CONFUSIONS = 3


def skeleton(word: str) -> str:
    word = word.lower().replace("ł", "l")
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()


@lru_cache
def lexicon() -> tuple[frozenset[str], dict[str, str]]:
    """(known words, skeleton -> most frequent word with that skeleton)."""
    known: set[str] = set()
    best: dict[str, tuple[int, str]] = {}
    for path in sorted((get_settings().config_dir / "lexicon").glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            word, _, count = line.partition("\t")
            n = int(count or 1)
            known.add(word)
            key = skeleton(word)
            if key not in best or n > best[key][0]:
                best[key] = (n, word)
    return frozenset(known), {key: word for key, (_, word) in best.items()}


def _with_case(template: str, word: str) -> str:
    if template.isupper():
        return word.upper()
    if template[0].isupper():
        return word[0].upper() + word[1:]
    return word


def fix_word(word: str) -> str:
    known, by_skeleton = lexicon()
    lower = word.lower().replace("ž", "ż")
    if lower in known:
        return _with_case(word, lower) if lower != word.lower() else word
    positions = [i for i, ch in enumerate(lower) if ch in CONFUSIONS][:MAX_CONFUSIONS]
    for n in range(len(positions) + 1):  # fewest substitutions first
        for chosen in itertools.combinations(positions, n):
            chars = list(lower)
            for i in chosen:
                chars[i] = CONFUSIONS[chars[i]]
            substituted = "".join(chars)
            if chosen and substituted in known:  # "infrastrukturq" -> "infrastrukturą", not "-a"
                return _with_case(word, substituted)
            candidate = by_skeleton.get(skeleton(substituted))
            if candidate:
                return _with_case(word, candidate)
    return word


AMOUNT_ZL = re.compile(r"(?<=\d)(\s*)z[tl1i](?![^\W\d_])")  # "7 500 zt" -> "7 500 zł"


COMPANY_FORM = re.compile(r"\b([Ss]p\.?\s*z\s*)[0O]\.\s*[0oO]\.")  # "Sp. z 0.o." -> "Sp. z o.o."
# reference numbers are upper case: "DA.zP.242.50.2026" -> "DA.ZP.242.50.2026", "zP/107/2026" -> "ZP/107/2026"
REFERENCE = re.compile(r"(?<![\w@.])[A-Za-z]{1,6}(?:[./][A-Za-z0-9]{1,8}){2,}(?![\w@])")


def _upper_reference(match: re.Match) -> str:
    token = match.group()
    letters = [c for c in token if c.isalpha()]
    if "www" in token.lower() or sum(c.isupper() for c in letters) * 2 < len(letters):
        return token
    return token.upper()


def fix_text(text: str) -> str:
    text = text.replace("ž", "ż").replace("Ž", "Ż")
    text = COMPANY_FORM.sub(lambda m: m.group(1) + "o.o.", text)
    text = REFERENCE.sub(_upper_reference, text)
    text = AMOUNT_ZL.sub(lambda m: m.group(1) + "zł", text)
    return WORD.sub(lambda m: fix_word(m.group()), text)
