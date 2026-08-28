"""The deterministic layer: retrieval, routing, no-answer, and phrase checks, no model
(rag-evaluation spec, *Retrieval and routing are scored deterministically*)."""

from dataclasses import asdict, dataclass, field

from harness.cases import Case

# Mirrors backend/rag/prompts.py:NO_ANSWER_MESSAGE's opening; the evaluator cannot import
# the application, and the message is frozen for the Day 6 baseline.
NO_ANSWER_PREFIX = "I wasn't able to find this in my sources"


@dataclass
class Deterministic:
    """Each check is True/False, or None when the case does not expect it."""

    retrieval_hit: bool | None = None
    provenance_ok: bool | None = None
    intent_ok: bool | None = None
    tools_ok: bool | None = None
    no_answer_ok: bool | None = None
    phrases_ok: bool | None = None
    plan_items_ok: bool | None = None
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def passed(self) -> bool:
        return not self.failures


def is_no_answer(answer: str, citations: list[dict]) -> bool:
    return answer.strip().startswith(NO_ANSWER_PREFIX) and not citations


def score(case: Case, response: dict) -> Deterministic:
    """Score one (case, strategy) response from `/api/ask` or `/api/chat`."""
    expect = case.expect
    answer: str = response.get("answer", "")
    citations: list[dict] = response.get("citations", [])
    result = Deterministic()

    no_answer = is_no_answer(answer, citations)
    if expect.no_answer or case.category == "out_of_domain" or citations or expect.documents:
        result.no_answer_ok = no_answer == expect.no_answer
        if not result.no_answer_ok:
            result.failures.append(
                "no-answer given" if no_answer else "answered but no-answer expected"
            )

    if expect.documents:
        cited = {c.get("document_id") for c in citations}
        result.retrieval_hit = any(doc in cited for doc in expect.documents)
        if not result.retrieval_hit:
            result.failures.append(
                f"none of {expect.documents} cited (got {sorted(filter(None, cited))})"
            )

    if citations:
        result.provenance_ok = all(c.get("source") and c.get("year") for c in citations)
        if not result.provenance_ok:
            result.failures.append("a citation lacks source or year")

    if expect.intent is not None:
        result.intent_ok = response.get("intent") == expect.intent
        if not result.intent_ok:
            result.failures.append(f"intent {response.get('intent')!r} != {expect.intent!r}")

    if expect.tools:
        ok = {t["name"] for t in response.get("tools", []) if t.get("status") == "ok"}
        result.tools_ok = all(tool in ok for tool in expect.tools)
        if not result.tools_ok:
            result.failures.append(f"tools ok={sorted(ok)} missing {expect.tools}")

    if expect.must_include or expect.must_not_include:
        lowered = answer.lower()
        missing = [p for p in expect.must_include if not _any_alternative(p, lowered)]
        present = [p for p in expect.must_not_include if _any_alternative(p, lowered)]
        result.phrases_ok = not missing and not present
        if missing:
            result.failures.append(f"missing phrase(s) {missing}")
        if present:
            result.failures.append(f"forbidden phrase(s) {present}")

    if expect.plan_must_not_include:
        items = plan_item_names(response)
        offending = [
            food
            for food in expect.plan_must_not_include
            if any(food.lower() in item for item in items)
        ]
        result.plan_items_ok = not offending
        if offending:
            result.failures.append(f"plan items include {offending}")

    return result


def _any_alternative(phrase: str, lowered_answer: str) -> bool:
    return any(alt.strip().lower() in lowered_answer for alt in phrase.split("|"))


def plan_item_names(response: dict) -> list[str]:
    """Lower-cased names of every item in every successful meal plan the chat produced."""
    names: list[str] = []
    for tool in response.get("tools", []):
        if tool.get("name") == "generate_meal_plan" and tool.get("status") == "ok":
            for item in (tool.get("result") or {}).get("items", []):
                names.append(str(item.get("name", "")).lower())
    return names
