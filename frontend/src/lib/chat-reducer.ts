// Pure reducer: chat stream events → the assistant message being built (design.md
// Decision 10). The hook owns the network; this owns the shape.

import type {
  ChatSseEvent,
  Citation,
  Intent,
  RetrievalMeta,
  ToolActivity,
} from "./api-types";

export type AssistantStatus = "streaming" | "done" | "error" | "interrupted";

export interface AssistantMessage {
  id: string;
  role: "assistant";
  intent: Intent | null;
  planned: string[];
  tools: ToolActivity[];
  text: string;
  citations: Citation[];
  retrieval: RetrievalMeta | null;
  disclaimer: string | null;
  status: AssistantStatus;
  error: string | null;
}

export interface UserMessage {
  id: string;
  role: "user";
  text: string;
}

export type ChatMessage = UserMessage | AssistantMessage;

export type AssistantAction =
  | { type: "event"; event: ChatSseEvent }
  | { type: "interrupted"; message: string }
  | { type: "failed"; message: string };

export function emptyAssistantMessage(id: string): AssistantMessage {
  return {
    id,
    role: "assistant",
    intent: null,
    planned: [],
    tools: [],
    text: "",
    citations: [],
    retrieval: null,
    disclaimer: null,
    status: "streaming",
    error: null,
  };
}

export function applyEvent(message: AssistantMessage, event: ChatSseEvent): AssistantMessage {
  switch (event.event) {
    case "route":
      return { ...message, intent: event.data.intent, planned: event.data.planned };
    case "tool":
      return { ...message, tools: [...message.tools, event.data] };
    case "token":
      return { ...message, text: message.text + event.data.text };
    case "final":
      return {
        ...message,
        intent: event.data.intent,
        citations: event.data.citations,
        retrieval: event.data.retrieval,
        disclaimer: event.data.disclaimer,
      };
    case "done":
      return { ...message, status: "done" };
    case "error":
      return { ...message, status: "error", error: event.data.message };
    default:
      return message;
  }
}

export function reduceAssistant(
  message: AssistantMessage,
  action: AssistantAction,
): AssistantMessage {
  switch (action.type) {
    case "event":
      return applyEvent(message, action.event);
    case "interrupted":
      return message.status === "done"
        ? message
        : { ...message, status: "interrupted", error: action.message };
    case "failed":
      return { ...message, status: "error", error: action.message };
  }
}

/** Text the reducer should keep when a stream ends badly: everything received so far. */
export function hasPartialText(message: AssistantMessage): boolean {
  return message.text.length > 0;
}
