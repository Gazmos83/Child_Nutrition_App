"""The test set: shape validation and fixture resolution (rag-evaluation spec)."""

import datetime as dt
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "rag_basic", "rag_advanced", "tool", "hybrid", "user_data", "out_of_domain", "adversarial"
]
# Which endpoint a category is evaluated through (design.md Decision 2).
ASK_CATEGORIES: frozenset[str] = frozenset({"rag_basic", "rag_advanced", "out_of_domain"})
# Which categories are judged with RAGAs when they received an answer.
JUDGED_CATEGORIES: frozenset[str] = frozenset({"rag_basic", "rag_advanced", "hybrid"})


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[str] = Field(default_factory=list)
    intent: Literal["rag", "tool", "hybrid"] | None = None
    tools: list[str] = Field(default_factory=list)
    no_answer: bool = False
    reference: str | None = None
    reference_source: str | None = None
    # Phrases are case-insensitive substrings; "a|b" means any of the alternatives.
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    # Foods that must not appear among a generated meal plan's *items* (the answer text may
    # legitimately name them in its "excluded foods" explanation).
    plan_must_not_include: list[str] = Field(default_factory=list)


class FeedFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days_ago: int = Field(ge=0, le=30)
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    feeding_type: Literal["breastmilk", "formula", "solid", "water"]
    food_id: str | None = None
    quantity: float | None = None
    unit: Literal["ml", "g"] = "ml"

    def resolve(self, now: dt.datetime) -> dict:
        """The entry as `POST /api/children/{id}/feedings` takes it, dated relative to now."""
        hour, minute = (int(part) for part in self.time.split(":"))
        day = (now - dt.timedelta(days=self.days_ago)).date()
        fed_at = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=dt.UTC)
        entry: dict = {
            "fed_at": fed_at.isoformat(),
            "feeding_type": self.feeding_type,
            "unit": self.unit,
        }
        if self.food_id is not None:
            entry["food_id"] = self.food_id
        if self.quantity is not None:
            entry["quantity"] = self.quantity
        return entry


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: Category
    question: str = Field(min_length=1)
    child: dict | None = None
    feeding_log: list[FeedFixture] = Field(default_factory=list)
    expect: Expect

    @property
    def endpoint(self) -> Literal["ask", "chat"]:
        return "ask" if self.category in ASK_CATEGORIES else "chat"

    @property
    def judged(self) -> bool:
        return self.category in JUDGED_CATEGORIES

    @model_validator(mode="after")
    def _chat_cases_have_a_child(self) -> Case:
        if self.endpoint == "chat" and self.child is None:
            raise ValueError(f"{self.id}: chat cases need a child fixture")
        if self.judged and not (self.expect.reference and self.expect.reference_source):
            raise ValueError(f"{self.id}: judged cases need a reference and its source")
        return self


class CaseSet(BaseModel):
    cases: list[Case]

    @model_validator(mode="after")
    def _unique_ids(self) -> CaseSet:
        ids = [c.id for c in self.cases]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate case ids: {duplicates}")
        return self


def load_cases(path: Path) -> CaseSet:
    """Load the file, resolving `child` / `feeding_log` fixture names into their values."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    fixtures: dict = raw.get("fixtures", {})
    cases = []
    for entry in raw["cases"]:
        entry = dict(entry)
        if isinstance(entry.get("child"), str):
            entry["child"] = fixtures[entry["child"]]
        if isinstance(entry.get("feeding_log"), str):
            entry["feeding_log"] = fixtures[entry["feeding_log"]]
        cases.append(entry)
    return CaseSet(cases=cases)
