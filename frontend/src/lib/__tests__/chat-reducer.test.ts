import { describe, expect, it } from "vitest";
import type { ToolActivity } from "../api-types";
import { applyEvent, emptyAssistantMessage, reduceAssistant } from "../chat-reducer";

const okTool: ToolActivity = {
  name: "calculate_bmi",
  status: "ok",
  args: { weight_kg: 8.5, height_cm: 70 },
  used_context: ["weight_kg"],
  result: { bmi: 17.35 },
  error: null,
  detail: null,
};
const failedTool: ToolActivity = {
  ...okTool,
  name: "lookup_food",
  status: "error",
  result: null,
  error: "We don't know a food called “nope” yet — try picking one from the list",
  detail: "Unknown food id 'nope'",
};

describe("chat reducer", () => {
  it("starts empty and streaming", () => {
    const m = emptyAssistantMessage("a1");
    expect(m.status).toBe("streaming");
    expect(m.text).toBe("");
    expect(m.tools).toEqual([]);
  });

  it("route sets intent and planned tools", () => {
    const m = applyEvent(emptyAssistantMessage("a1"), {
      event: "route",
      data: { intent: "hybrid", planned: ["calculate_bmi", "search_guidelines"] },
    });
    expect(m.intent).toBe("hybrid");
    expect(m.planned).toEqual(["calculate_bmi", "search_guidelines"]);
  });

  it("tool events append ok and error activities in order", () => {
    let m = applyEvent(emptyAssistantMessage("a1"), { event: "tool", data: okTool });
    m = applyEvent(m, { event: "tool", data: failedTool });
    expect(m.tools.map((t) => t.status)).toEqual(["ok", "error"]);
    expect(m.tools[1].error).toContain("nope");
  });

  it("tokens append", () => {
    let m = applyEvent(emptyAssistantMessage("a1"), { event: "token", data: { text: "Hello " } });
    m = applyEvent(m, { event: "token", data: { text: "there" } });
    expect(m.text).toBe("Hello there");
  });

  it("final sets citations, retrieval and disclaimer; done completes", () => {
    let m = applyEvent(emptyAssistantMessage("a1"), {
      event: "final",
      data: {
        citations: [
          {
            index: 1,
            source: "Iron Source",
            year: 2010,
            topic: "iron",
            section: null,
            document_id: "iron",
            score: 0.8,
            excerpt: "…",
          },
        ],
        retrieval: null,
        disclaimer: "Not medical advice.",
        intent: "rag",
        tools: [],
      },
    });
    expect(m.citations[0].source).toBe("Iron Source");
    expect(m.disclaimer).toBe("Not medical advice.");
    m = applyEvent(m, { event: "done", data: {} });
    expect(m.status).toBe("done");
  });

  it("error event keeps received text and records the message", () => {
    let m = applyEvent(emptyAssistantMessage("a1"), { event: "token", data: { text: "partial" } });
    m = applyEvent(m, { event: "error", data: { message: "We lost the thread mid-answer." } });
    expect(m.status).toBe("error");
    expect(m.text).toBe("partial");
    expect(m.error).toBe("We lost the thread mid-answer.");
  });

  it("interrupted keeps text and is ignored once done", () => {
    let m = applyEvent(emptyAssistantMessage("a1"), { event: "token", data: { text: "half" } });
    m = reduceAssistant(m, { type: "interrupted", message: "dropped" });
    expect(m.status).toBe("interrupted");
    expect(m.text).toBe("half");
    const done = applyEvent(m, { event: "done", data: {} });
    expect(reduceAssistant(done, { type: "interrupted", message: "late" }).status).toBe("done");
  });

  it("failed before any event marks the message as error", () => {
    const m = reduceAssistant(emptyAssistantMessage("a1"), {
      type: "failed",
      message: "We couldn't reach the chef.",
    });
    expect(m.status).toBe("error");
    expect(m.error).toContain("chef");
  });
});
