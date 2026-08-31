import { describe, expect, it } from "vitest";
import type { RetrievalMeta, ToolActivity } from "../api-types";
import { emptyAssistantMessage, type AssistantMessage } from "../chat-reducer";
import { toolSteps } from "../tool-steps";

function activity(name: string, status: "ok" | "error" = "ok"): ToolActivity {
  return {
    name,
    status,
    args: {},
    used_context: [],
    result: status === "ok" ? {} : null,
    error: status === "error" ? "went wrong" : null,
    detail: null,
  };
}

const RETRIEVAL: RetrievalMeta = {
  strategy: "advanced",
  queries: ["iron"],
  filters: {},
  filter_dropped: false,
  retrieved: 8,
  kept: 4,
  top_score: 0.71,
};

function message(overrides: Partial<AssistantMessage>): AssistantMessage {
  return { ...emptyAssistantMessage("m1"), ...overrides };
}

describe("toolSteps", () => {
  it("shows every planned step as pending the moment routing lands", () => {
    const steps = toolSteps(message({ planned: ["calculate_bmi", "generate_meal_plan"] }));
    expect(steps).toEqual([
      { name: "calculate_bmi", status: "pending", activity: null },
      { name: "generate_meal_plan", status: "pending", activity: null },
    ]);
  });

  it("resolves steps by name as results arrive, keeping the planned order", () => {
    // run_tools runs the planner last, so its result arrives after the others even
    // though the router planned it first.
    const plan = activity("generate_meal_plan");
    const bmi = activity("calculate_bmi");
    const steps = toolSteps(
      message({ planned: ["generate_meal_plan", "calculate_bmi"], tools: [bmi, plan] }),
    );
    expect(steps).toEqual([
      { name: "generate_meal_plan", status: "ok", activity: plan },
      { name: "calculate_bmi", status: "ok", activity: bmi },
    ]);
  });

  it("keeps a failed result failed and a still-missing one pending", () => {
    const failed = activity("lookup_food", "error");
    const steps = toolSteps(message({ planned: ["lookup_food", "calculate_bmi"], tools: [failed] }));
    expect(steps).toEqual([
      { name: "lookup_food", status: "error", activity: failed },
      { name: "calculate_bmi", status: "pending", activity: null },
    ]);
  });

  it("appends results the router never planned, so nothing that ran is hidden", () => {
    // run_tools adds an implicit detect_nutrient_gaps before the planner when the
    // request carries a feeding log.
    const gaps = activity("detect_nutrient_gaps");
    const plan = activity("generate_meal_plan");
    const steps = toolSteps(message({ planned: ["generate_meal_plan"], tools: [gaps, plan] }));
    expect(steps).toEqual([
      { name: "generate_meal_plan", status: "ok", activity: plan },
      { name: "detect_nutrient_gaps", status: "ok", activity: gaps },
    ]);
  });

  it("matches repeated planned names to results one at a time, in arrival order", () => {
    const first = activity("lookup_food");
    const steps = toolSteps(
      message({ planned: ["lookup_food", "lookup_food"], tools: [first] }),
    );
    expect(steps).toEqual([
      { name: "lookup_food", status: "ok", activity: first },
      { name: "lookup_food", status: "pending", activity: null },
    ]);
  });

  it("treats the guideline search as done once retrieval arrives, since it never emits a tool event", () => {
    const planned = ["search_guidelines", "calculate_bmi"];
    expect(toolSteps(message({ planned }))[0]).toEqual({
      name: "search_guidelines",
      status: "pending",
      activity: null,
    });
    expect(toolSteps(message({ planned, retrieval: RETRIEVAL }))[0]).toEqual({
      name: "search_guidelines",
      status: "ok",
      activity: null,
    });
  });

  it("demotes leftover pending steps to skipped when the stream ends", () => {
    const steps = toolSteps(
      message({ planned: ["search_guidelines", "calculate_bmi"], status: "error" }),
    );
    expect(steps.map((s) => s.status)).toEqual(["skipped", "skipped"]);
  });

  it("returns nothing when nothing was planned and nothing ran", () => {
    expect(toolSteps(message({}))).toEqual([]);
  });
});
