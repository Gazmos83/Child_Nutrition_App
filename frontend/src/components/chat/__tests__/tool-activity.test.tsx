import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ToolActivity } from "@/lib/api-types";
import { emptyAssistantMessage, type AssistantMessage } from "@/lib/chat-reducer";
import * as copy from "@/lib/copy";
import { toolSteps } from "@/lib/tool-steps";
import { ToolActivityList } from "../tool-activity";

const okTool: ToolActivity = {
  name: "calculate_bmi",
  status: "ok",
  args: { weight_kg: 8.4, height_cm: 68 },
  used_context: ["weight_kg", "height_cm"],
  result: { bmi: 18.2 },
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

function message(overrides: Partial<AssistantMessage>): AssistantMessage {
  return { ...emptyAssistantMessage("m1"), ...overrides };
}

function renderList(m: AssistantMessage) {
  return render(<ToolActivityList steps={toolSteps(m)} streaming={m.status === "streaming"} />);
}

describe("ToolActivityList", () => {
  it("shows planned steps as pending work before any result arrives", () => {
    renderList(message({ planned: ["calculate_bmi", "generate_meal_plan"] }));
    const chips = screen.getAllByTestId("tool-chip");
    expect(chips).toHaveLength(2);
    for (const chip of chips) expect(chip).toHaveAttribute("data-status", "pending");
    expect(screen.getAllByText(copy.TOOL_STEP_PENDING)).toHaveLength(2);
    expect(chips[0]).toBeVisible();
  });

  it("summarises a finished tool in words, not JSON", () => {
    renderList(message({ planned: ["calculate_bmi"], tools: [okTool], status: "streaming" }));
    expect(screen.getByText("BMI from 8.4 kg and 68 cm")).toBeInTheDocument();
    expect(screen.queryByText(/"bmi": 18.2/)).toBeNull();
  });

  it("keeps a failed tool visible with its message, even after the answer is done", () => {
    renderList(message({ planned: ["lookup_food"], tools: [failedTool], status: "done" }));
    const chip = screen.getByTestId("tool-chip");
    expect(chip).toHaveAttribute("data-status", "error");
    expect(chip).toBeVisible();
    expect(screen.getByText(`${copy.TOOL_CHIP_FAILED} — ${copy.toolLabel("lookup_food")}`)).toBeVisible();
    expect(screen.getByText(failedTool.error as string)).toBeVisible();
  });

  it("keeps raw arguments and result reachable on request", () => {
    renderList(message({ planned: ["calculate_bmi"], tools: [okTool], status: "streaming" }));
    fireEvent.click(screen.getByRole("button", { name: copy.SHOW_DETAILS }));
    const raw = screen.getByText(/"weight_kg": 8.4/);
    expect(raw).toBeVisible();
    expect(raw.textContent).toContain('"bmi": 18.2');
    fireEvent.click(screen.getByRole("button", { name: copy.HIDE_DETAILS }));
    expect(screen.queryByText(/"weight_kg": 8.4/)).toBeNull();
  });

  it("collapses a clean finished run behind the summary toggle, and reopens on request", () => {
    renderList(message({ planned: ["calculate_bmi"], tools: [okTool], status: "done" }));
    expect(screen.queryByTestId("tool-chip")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: copy.TOOLS_USED }));
    expect(screen.getByTestId("tool-chip")).toBeVisible();
  });

  it("renders nothing when no work was planned or run", () => {
    const { container } = renderList(message({}));
    expect(container).toBeEmptyDOMElement();
  });
});
