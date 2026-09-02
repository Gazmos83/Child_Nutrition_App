import { describe, expect, it } from "vitest";
import type { NoteOutcome } from "../api-types";
import type { ChatMessage } from "../chat-reducer";
import { latestNoteOutcomes, outcomeFor } from "../note-outcomes";

const OUTCOMES: NoteOutcome[] = [
  { index: 0, kind: "doctor", text: "no honey", applied: true, detail: "left one food out" },
  { index: 1, kind: "preference", text: "no kale chips", applied: false, detail: "not in our table" },
];

function assistant(id: string, tools: unknown[]): ChatMessage {
  return {
    id,
    role: "assistant",
    intent: "tool",
    planned: [],
    tools,
    text: "",
    citations: [],
    retrieval: null,
    disclaimer: null,
    status: "done",
    error: null,
  } as unknown as ChatMessage;
}

function user(id: string): ChatMessage {
  return { id, role: "user", content: "hi" } as unknown as ChatMessage;
}

function planTool(note_outcomes: NoteOutcome[]) {
  return {
    name: "generate_meal_plan",
    status: "ok" as const,
    args: {},
    used_context: [],
    result: { outcome: "plan", items: [], overrides: [], message: "m", note_outcomes },
    error: null,
    detail: null,
  };
}

describe("latestNoteOutcomes", () => {
  it("reads the newest plan's outcomes and ignores messages without a plan", () => {
    const messages: ChatMessage[] = [
      user("u1"),
      assistant("a1", [planTool([OUTCOMES[0]])]),
      assistant("a2", []),
      assistant("a3", [planTool(OUTCOMES)]),
      user("u2"),
    ];
    expect(latestNoteOutcomes(messages)).toEqual(OUTCOMES);
    expect(latestNoteOutcomes([])).toEqual([]);
  });

  it("matches a not-applied outcome by kind and trimmed text only", () => {
    expect(outcomeFor(OUTCOMES, "preference", "  no kale chips ")?.detail).toBe("not in our table");
    expect(outcomeFor(OUTCOMES, "doctor", "no kale chips")).toBeUndefined();
    expect(outcomeFor(OUTCOMES, "doctor", "no honey")).toBeUndefined(); // applied rows are not marked
  });
});
