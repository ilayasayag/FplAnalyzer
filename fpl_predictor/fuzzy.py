"""Name-matching used to map external data feeds (FIFA fantasy, ESPN) onto our
synthetic player pool. Extracted verbatim from the FIFA-alignment matcher in
fifa_fantasy_squads/_fuzzy_match.py so the live ingester can import it cleanly.
"""
import re
import unicodedata
from difflib import SequenceMatcher

MANUAL = {
    "ø": "o", "œ": "oe", "æ": "ae", "ß": "ss", "đ": "d", "ð": "d",
    "ł": "l", "ı": "i", "þ": "th", "ħ": "h", "ŧ": "t", "ʿ": "", "ʾ": "",
}


def translit(s: str) -> str:
    s = (s or "").lower()
    s = "".join(MANUAL.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", " ").replace(".", " ").replace("-", " ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return [t for t in translit(s).split(" ") if t]


def score(a, b):
    """Higher = more likely the same player. 0 = reject."""
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    ratio = SequenceMatcher(None, translit(a), translit(b)).ratio()
    last_eq = ta[-1] == tb[-1]
    first_eq = ta[0] == tb[0]
    first_init = ta[0][:1] == tb[0][:1]
    subset = sa <= sb or sb <= sa
    jacc = len(sa & sb) / len(sa | sb)
    if last_eq and (first_eq or first_init):
        return 0.95 + 0.05 * ratio
    if subset and (sa & sb):
        return 0.90 + 0.05 * ratio
    if ratio >= 0.84:
        return 0.80 + 0.10 * ratio
    if last_eq and jacc >= 0.5:
        return 0.70 + 0.10 * ratio
    if (ta[-1] in sb or tb[-1] in sa) and ratio >= 0.6:
        return 0.60 + 0.10 * ratio
    return 0.0
