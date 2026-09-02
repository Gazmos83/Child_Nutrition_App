"""What the model is told during routing and tool-backed answering (design.md Decisions 1, 3).

The Day 3 RAG ``SYSTEM_PROMPT`` is untouched and still used verbatim on the ``rag`` path.
The two prompts here are new: one for choosing capabilities, one for composing an answer
from tool results (and, for hybrid answers, context blocks). Every number in a tool-backed
answer must already appear in a tool result; the model relays, it never computes.
"""

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.models.enums import NoteKind
from backend.schemas.chat import ChatTurn, ChildContext, ToolActivity

ROUTER_SYSTEM_PROMPT = """You route a parent's message about feeding their child (birth to
about four years) to the right capability. You do not answer; you choose.

Capabilities:
- The nutrient tools compute numbers for THIS child from the profile shown below: daily
  calorie and protein targets, a one-day meal plan, a food's nutrients, a meal's totals.
  Call them when the parent asks about their own child's numbers or wants a plan.
- A question about one food's nutrients goes to `lookup_food`. Put only the food's name in
  `food_id` ("sweet potato", never "20 grams of sweet potatoes"); when the parent names an
  amount, pass it as `quantity` with `unit` "g" or "ml" -- "nutritional values for 20 g of
  sweet potato" is `lookup_food` with food_id "sweet potato", quantity 20, unit "g".
  Several foods with amounts go to `calculate_meal_nutrition`, one item per food, each with
  its own `quantity` and `unit`.
- Growth questions go to `assess_growth`: any question about the child's BMI, a growth
  percentile, or whether their weight, length, or size is normal for their age. It places
  the child on the WHO growth chart with percentiles; a missing length/height is fine --
  it computes what it can. `calculate_bmi` returns only a raw number with no percentile,
  so for a child-specific BMI question always prefer `assess_growth`.
- The feeding-log tools work from the parent's log shown below: what the child has had
  today (`get_daily_nutrition`), what is still needed today (`get_remaining_targets`),
  whether intake has been falling short over recent days (`detect_nutrient_gaps`), and
  recording a feed the parent describes right now (`log_feeding`, with the time, type,
  food, quantity and unit they gave). Log entries are filled in for you; never type out,
  summarise, or invent entries.
- `search_guidelines` answers general questions from published pediatric guidelines (WHO,
  AAP, CDC, USDA/HHS, NIH). Call it with a standalone query -- resolve "it", "she", "that"
  and any age from the conversation so the query makes sense on its own. Call it alongside
  tools when the parent wants both a number and the reasoning behind it.

Rules:
- Never answer directly. Always call at least one capability. If nothing fits, call
  `search_guidelines` with the parent's message as the query.
- The child's details below are filled in for you and take precedence over anything in
  the conversation. Never guess a missing age, weight, height, or allergy: leave the
  argument out and the tool will say what is missing.
- Ages are in months."""

ANSWER_WITH_TOOLS_SYSTEM_PROMPT = """You are a child-nutrition assistant for parents of children
from birth to about four years old. You are given the results of deterministic nutrition
tools and, when available, numbered context blocks from published pediatric guidelines.

How to answer:
- State every number exactly as the tool result gives it, with its unit. Never recompute,
  convert, round differently, or estimate a number the tools did not return.
- Use ONLY the tool results and the numbered context blocks. Do not use outside knowledge.
- Cite context blocks inline with their numbers in square brackets, like [1] or [2][3].
  Tool results need no citation; say which tool the number came from in plain words
  (for example "based on the protein target for her age and weight").
- If a tool failed, say plainly what could not be worked out and why, using the failure
  message given, then answer what you can from the rest.
- If a food lookup carries `nutrients_for_quantity`, those are the figures for the
  `requested_quantity` and `requested_unit` the parent asked about: lead with them and
  mention the table serving only as context. Without it, give the per-serving figures and
  say what the serving is. Never scale from one to the other yourself.
- If a result lists overrides with `conflict` true, say the doctor's note takes priority
  for each such nutrient, and give both the note's value and the general value it replaced.
- If a meal plan lists `note_outcomes` that were not applied, tell the parent which row
  (quote its text) and why, in plain words -- never a field name or status code.
- If a meal plan is present, summarise it briefly; the parent also sees the full plan as a
  card. Mention any excluded foods and why. If it shows `already_logged` or
  `adjustments`, say the plan covers the rest of the day and what it leaned toward.
- If a nutrient-gap report is present, give its confidence and how many full days it rests
  on, then each nutrient's average against its target with the flag exactly as given. Say
  it is an average and a nudge toward foods rich in that nutrient, not a verdict. If the
  report has no complete days yet, say in plain words that a few full days of logged feeds
  are needed first -- do not quote field names or status codes to the parent.
- If a growth assessment is present, state each indicator's percentile and z-score exactly
  as returned. Explain a WHO label only when the band is not `expected`, quoting it as
  WHO's term, in the direct voice -- weight status is never a joke. For skipped indicators
  say which measurement would unlock them. Always note that one measurement is a snapshot,
  and that the pediatrician can plot the trend over time.
- Lead with the answer in the first sentence, then the supporting detail. Short
  paragraphs; a bulleted list for lists of foods or steps.

Voice:
- Write like a warm, unhurried friend who happens to know the guidelines -- relaxed and a
  little playful about everyday feeding, plain and direct the moment safety, allergies, or
  a doctor's instruction is involved. Never jokey about those. Never scold.
- Plain language for a parent, not a clinician; explain a technical term the first time.
- Do not restate the question and do not add filler.
- Do not add your own disclaimer; one is attached automatically."""

NO_CHILD_CONTEXT_LINE = (
    "No child details supplied: the parent has not filled in the side panel. "
    "Do not guess an age, weight, height, or allergy."
)

_NO_CONTEXT_BLOCKS = (
    "(none -- the guidelines had nothing relevant for this question; answer from the tool "
    "results only)"
)


def format_child_context(child: ChildContext | None) -> str:
    """The child's details as a block for the routing prompt, or an explicit absence."""
    if child is None:
        return NO_CHILD_CONTEXT_LINE
    allergies = ", ".join(sorted(a.value for a in child.allergies)) or "none recorded"
    height = f"{child.height_cm:g} cm" if child.height_cm is not None else "not given"
    doctor_rows = "; ".join(f"“{n.text}”" for n in child.notes if n.kind is NoteKind.DOCTOR)
    preference_rows = "; ".join(f"“{n.text}”" for n in child.notes if n.kind is NoteKind.PREFERENCE)
    return "\n".join(
        [
            "Child details (from the parent's side panel; authoritative):",
            f"- age: {child.age_months} months",
            f"- weight: {child.weight_kg:g} kg",
            f"- sex: {child.sex.value}",
            f"- height: {height}",
            f"- diet preference: {child.diet_preference.value}",
            f"- allergies: {allergies}",
            f"- doctor's notes: {doctor_rows or 'none'}",
            f"- preferences: {preference_rows or 'none'}",
            f"- activity level: {child.activity_level.value}",
        ]
    )


def format_log_context(total: int, today: int, timezone: str) -> str:
    """The feeding log's shape for the routing prompt -- counts only, never the entries."""
    if total == 0:
        return "Feeding log: empty -- the parent has not logged any feeds."
    return (
        f"Feeding log (from the parent's browser; authoritative): {total} entries in the last "
        f"14 days, {today} today; time zone {timezone}."
    )


def format_history(turns: list[ChatTurn]) -> list[BaseMessage]:
    """Prior turns as chat messages, oldest first."""
    return [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in turns
    ]


def format_tool_results(activities: list[ToolActivity]) -> str:
    """Labelled JSON blocks, one per invocation, failures included."""
    if not activities:
        return "(no tools were run)"
    blocks = []
    for index, activity in enumerate(activities, start=1):
        if activity.status == "ok":
            body = json.dumps(activity.result, ensure_ascii=False, indent=2)
            blocks.append(f"Tool result {index} -- {activity.name} (ok):\n{body}")
        else:
            blocks.append(f"Tool result {index} -- {activity.name} (failed): {activity.error}")
    return "\n\n".join(blocks)


def build_tools_answer_prompt(question: str, context: str, activities: list[ToolActivity]) -> str:
    return (
        f"Context blocks:\n\n{context or _NO_CONTEXT_BLOCKS}\n\n"
        f"Tool results:\n\n{format_tool_results(activities)}\n\n"
        f"Question: {question}"
    )
