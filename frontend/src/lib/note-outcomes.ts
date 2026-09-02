// The latest meal plan's verdict on each note row, read from the chat session so the Child
// tab can mark a row the plan could not apply where the parent typed it (child-notes-
// restrictions design Decision 7). Pure; no request, no LLM call.

import { isMealPlanResult, type NoteOutcome } from "./api-types";
import type { ChatMessage } from "./chat-reducer";

/** The `note_outcomes` of the newest meal plan in `messages`, or an empty list. */
export function latestNoteOutcomes(messages: readonly ChatMessage[]): NoteOutcome[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role !== "assistant") continue;
    const plan = message.tools
      .filter((t) => t.name === "generate_meal_plan" && t.status === "ok")
      .map((t) => t.result as unknown)
      .find(isMealPlanResult);
    if (plan) return plan.note_outcomes;
  }
  return [];
}

/** The not-applied outcome matching a row, by kind and trimmed text. */
export function outcomeFor(
  outcomes: readonly NoteOutcome[],
  kind: NoteOutcome["kind"],
  text: string,
): NoteOutcome | undefined {
  const trimmed = text.trim();
  return outcomes.find((o) => !o.applied && o.kind === kind && o.text === trimmed);
}
