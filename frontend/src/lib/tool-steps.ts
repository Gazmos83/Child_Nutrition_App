// Pure merge of the router's plan (`route.data.planned`) with the tool results that have
// arrived, so the UI can show work in progress the moment routing lands. chat-reducer owns
// the raw events; this owns the step view.
//
// Two backend realities shape the merge (backend/chat/service.py:run_tools):
// - Results keep the planned order except the meal planner, which always runs last, and an
//   implicit gap check may run that the router never planned — so match by name, never by
//   position, and never drop a result that has no planned entry.
// - `search_guidelines` never emits a `tool` event; the retrieval path answers for it, so
//   its completion signal is `retrieval` arriving with `final`.

import type { ToolActivity } from "./api-types";
import type { AssistantMessage } from "./chat-reducer";

export type ToolStepStatus = "pending" | "ok" | "error" | "skipped";

export interface ToolStep {
  name: string;
  status: ToolStepStatus;
  activity: ToolActivity | null;
}

const SEARCH_STEP = "search_guidelines";

export function toolSteps(message: AssistantMessage): ToolStep[] {
  const streaming = message.status === "streaming";
  const unclaimed = new Map<string, ToolActivity[]>();
  for (const activity of message.tools) {
    const queue = unclaimed.get(activity.name);
    if (queue) queue.push(activity);
    else unclaimed.set(activity.name, [activity]);
  }

  const steps: ToolStep[] = [];
  for (const name of message.planned) {
    const activity = unclaimed.get(name)?.shift() ?? null;
    if (activity) {
      steps.push({ name, status: activity.status, activity });
    } else if (name === SEARCH_STEP) {
      steps.push({
        name,
        status: message.retrieval ? "ok" : streaming ? "pending" : "skipped",
        activity: null,
      });
    } else {
      steps.push({ name, status: streaming ? "pending" : "skipped", activity: null });
    }
  }
  for (const queue of unclaimed.values()) {
    for (const activity of queue) {
      steps.push({ name: activity.name, status: activity.status, activity });
    }
  }
  return steps;
}
