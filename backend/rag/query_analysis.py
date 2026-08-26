"""Deterministic query analysis: the child's age, in months (Day 3 design.md Decision 2).

Pure Python, no model call. Age is the one piece of structure the advanced retriever
needs from the question, and parsing it is a closed problem with testable edge cases; a
model extraction would add cost and a failure mode to every query and would still need
validating (hard rule 7). Output is always a validated ``AgeRange`` bounded to 0-60
months (hard rule 1) or ``None``.

Known, accepted limitation: a duration that is not an age ("6 months ago I ...") is read
as an age. The consequence is only a metadata filter that is dropped again if it
eliminates every passage.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.db.knowledge_store import MAX_AGE_MONTHS, MIN_AGE_MONTHS

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "eighteen": 18,
    "twenty": 20,
    "twenty-four": 24,
}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"
_SEP = r"[\s-]*"
_OLD = r"(?:[\s-]*old)?"

_RANGE_MONTHS = re.compile(
    rf"\b{_NUM}{_SEP}(?:-|–|to|and)\s*{_NUM}{_SEP}(?:months?|mos?)\b", re.IGNORECASE
)
_RANGE_YEARS = re.compile(
    rf"\b{_NUM}{_SEP}(?:-|–|to|and)\s*{_NUM}{_SEP}(?:years?|yrs?)\b", re.IGNORECASE
)
_MONTHS = re.compile(rf"\b{_NUM}{_SEP}(?:months?|mos?)\b{_OLD}", re.IGNORECASE)
_YEARS = re.compile(rf"\b{_NUM}{_SEP}(?:years?|yrs?)\b{_OLD}", re.IGNORECASE)
_WEEKS = re.compile(rf"\b{_NUM}{_SEP}(?:weeks?|wks?)\b{_OLD}", re.IGNORECASE)

# Life-stage vocabulary, in months. Checked only when no numeric age is present.
_STAGES: list[tuple[re.Pattern[str], tuple[int, int]]] = [
    (re.compile(r"\bnew-?borns?\b|\bneonates?\b", re.IGNORECASE), (0, 1)),
    (re.compile(r"\bpre-?schoolers?\b|\bpre-?school\b", re.IGNORECASE), (36, 60)),
    (re.compile(r"\btoddlers?\b", re.IGNORECASE), (12, 36)),
    (re.compile(r"\binfants?\b|\bbab(?:y|ies)\b", re.IGNORECASE), (0, 12)),
]


class AgeRange(BaseModel):
    """An age range in months, inclusive, within the supported 0-60 span."""

    model_config = ConfigDict(frozen=True)

    min_months: int = Field(ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)
    max_months: int = Field(ge=MIN_AGE_MONTHS, le=MAX_AGE_MONTHS)

    @model_validator(mode="after")
    def _ordered(self) -> AgeRange:
        if self.min_months > self.max_months:
            raise ValueError("min_months must not exceed max_months")
        return self

    @property
    def is_exact(self) -> bool:
        return self.min_months == self.max_months


def _to_number(token: str) -> float:
    token = token.lower()
    return float(_NUMBER_WORDS.get(token, token if token.replace(".", "", 1).isdigit() else "nan"))


def _clamp(lo: int, hi: int) -> AgeRange | None:
    """Bound to 0-60; None when the whole range lies above the supported span."""
    if lo > MAX_AGE_MONTHS or hi < MIN_AGE_MONTHS:
        return None
    return AgeRange(min_months=max(lo, MIN_AGE_MONTHS), max_months=min(hi, MAX_AGE_MONTHS))


def extract_age_range(question: str) -> AgeRange | None:
    """Return the child's age as a month range, or None if the question names no age."""
    text = question.strip()
    if not text:
        return None
    # "2 and a half years" -> "2.5 years"
    text = re.sub(r"\b(\d+)\s+and\s+a\s+half\b", r"\1.5", text, flags=re.IGNORECASE)

    if m := _RANGE_MONTHS.search(text):
        lo, hi = sorted((_to_number(m.group(1)), _to_number(m.group(2))))
        return _clamp(int(lo), int(hi))
    if m := _RANGE_YEARS.search(text):
        lo, hi = sorted((_to_number(m.group(1)), _to_number(m.group(2))))
        return _clamp(int(lo * 12), int(hi * 12) + 11)

    years = _YEARS.search(text)
    months = _MONTHS.search(text)
    weeks = _WEEKS.search(text)

    if years and months:  # "2 years 3 months" -> exact
        total = int(_to_number(years.group(1)) * 12 + _to_number(months.group(1)))
        return _clamp(total, total)
    if months:
        value = _to_number(months.group(1))
        if value != value:  # NaN guard
            return None
        n = int(value)
        return _clamp(n, n)
    if years:
        value = _to_number(years.group(1))
        if value != value:
            return None
        if value != int(value):  # "2.5 years" -> that month, exactly
            n = int(round(value * 12))
            return _clamp(n, n)
        lo = int(value) * 12
        return _clamp(lo, lo + 11)
    if weeks:
        n = int(_to_number(weeks.group(1)) // 4)
        return _clamp(n, n)

    for pattern, (lo, hi) in _STAGES:
        if pattern.search(text):
            return AgeRange(min_months=lo, max_months=hi)
    return None
