"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import type { ChatRequest, ChatTurn, ChildContext, FeedingEntry } from "@/lib/api-types";
import {
  applyEvent,
  emptyAssistantMessage,
  loggedFeedingFrom,
  reduceAssistant,
  type AssistantMessage,
  type ChatMessage,
} from "@/lib/chat-reducer";
import * as copy from "@/lib/copy";
import { appendLoggedFeeding } from "@/lib/feeding-log-store";
import { parseSseFrames } from "@/lib/sse";

const MAX_HISTORY_TURNS = 12;

interface RunParams {
  text: string;
  assistantId: string;
  history: ChatTurn[];
}

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Completed turns before `upTo`, as the API expects them: text only, most recent 12. */
export function historyFrom(messages: ChatMessage[], upTo: number): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const m of messages.slice(0, upTo)) {
    if (m.role === "user") turns.push({ role: "user", content: m.text });
    else if (m.status === "done" && m.text) turns.push({ role: "assistant", content: m.text });
  }
  return turns.slice(-MAX_HISTORY_TURNS);
}

async function readDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : ""))
        .filter(Boolean)
        .join(" ");
    }
  } catch {
    // Not JSON; fall through to the status text.
  }
  return res.statusText;
}

/** What travels with every message besides the text: the side panel and the local log. */
export interface RequestContext {
  child: ChildContext | null;
  feeding_log: FeedingEntry[];
  timezone: string;
}

export function useChat(getContext: () => RequestContext) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const getContextRef = useRef(getContext);
  getContextRef.current = getContext;

  const patch = useCallback((id: string, fn: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((current) =>
      current.map((m) => (m.id === id && m.role === "assistant" ? fn(m) : m)),
    );
  }, []);

  const run = useCallback(
    async ({ text, assistantId, history }: RunParams) => {
      const context = getContextRef.current();
      const body: ChatRequest = {
        message: text,
        child: context.child,
        history,
        feeding_log: context.feeding_log,
        timezone: context.timezone,
        stream: true,
      };
      let res: Response;
      try {
        res = await fetch("/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
      } catch {
        patch(assistantId, (m) => reduceAssistant(m, { type: "failed", message: copy.UNREACHABLE }));
        return;
      }
      if (!res.ok) {
        const detail = await readDetail(res);
        const message = res.status === 503 ? copy.UNAVAILABLE(detail) : detail || copy.UNREACHABLE;
        patch(assistantId, (m) => reduceAssistant(m, { type: "failed", message }));
        return;
      }
      if (!res.body) {
        patch(assistantId, (m) => reduceAssistant(m, { type: "failed", message: copy.UNREACHABLE }));
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let carry = "";
      let sawEvent = false;
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          const parsed = parseSseFrames(decoder.decode(value, { stream: true }), carry);
          carry = parsed.carry;
          for (const event of parsed.events) {
            sawEvent = true;
            // A feed the assistant logged for the parent joins the local log (Decision 11).
            const logged = loggedFeedingFrom(event);
            if (logged) appendLoggedFeeding(logged);
            patch(assistantId, (m) => applyEvent(m, event));
          }
        }
      } catch {
        patch(assistantId, (m) =>
          reduceAssistant(
            m,
            sawEvent
              ? { type: "interrupted", message: copy.INTERRUPTED }
              : { type: "failed", message: copy.UNREACHABLE },
          ),
        );
        return;
      }
      // The stream closed without `done` or `error`: treat as interrupted, keep the text.
      patch(assistantId, (m) =>
        m.status === "streaming"
          ? reduceAssistant(m, { type: "interrupted", message: copy.INTERRUPTED })
          : m,
      );
    },
    [patch],
  );

  const mutation = useMutation({ mutationFn: run });

  const send = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text || mutation.isPending) return;
      const assistantId = newId();
      let history: ChatTurn[] = [];
      setMessages((current) => {
        history = historyFrom(current, current.length);
        return [
          ...current,
          { id: newId(), role: "user", text },
          emptyAssistantMessage(assistantId),
        ];
      });
      // `history` is read synchronously by the updater above before mutate runs.
      queueMicrotask(() => mutation.mutate({ text, assistantId, history }));
    },
    [mutation],
  );

  const retry = useCallback(
    (assistantId: string) => {
      if (mutation.isPending) return;
      let params: RunParams | null = null;
      setMessages((current) => {
        const index = current.findIndex((m) => m.id === assistantId);
        const user = index > 0 ? current[index - 1] : null;
        if (index < 0 || !user || user.role !== "user") return current;
        params = { text: user.text, assistantId, history: historyFrom(current, index - 1) };
        return current.map((m) => (m.id === assistantId ? emptyAssistantMessage(assistantId) : m));
      });
      queueMicrotask(() => {
        if (params) mutation.mutate(params);
      });
    },
    [mutation],
  );

  return { messages, send, retry, isPending: mutation.isPending };
}
