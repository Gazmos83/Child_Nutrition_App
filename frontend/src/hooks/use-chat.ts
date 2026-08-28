"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { notifyUnauthorized, readDetail } from "@/lib/api";
import type { ChatRequest, ChatTurn, LoggedFeeding } from "@/lib/api-types";
import {
  applyEvent,
  emptyAssistantMessage,
  loggedFeedingFrom,
  reduceAssistant,
  type AssistantMessage,
  type ChatMessage,
} from "@/lib/chat-reducer";
import * as copy from "@/lib/copy";
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

/**
 * What travels with every message besides the text. The child's details and log live on
 * the account; the request names the child and the server reads the rest.
 */
export interface RequestContext {
  childId: string | null;
  timezone: string;
  /** A feed the assistant logged mid-answer, to be saved to the account's log. */
  onFeedLogged: (logged: LoggedFeeding) => void;
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
        child_id: context.childId,
        history,
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
      if (res.status === 401) {
        // The session ended between page load and send: back to sign-in, message kept.
        patch(assistantId, (m) =>
          reduceAssistant(m, { type: "failed", message: copy.SESSION_EXPIRED }),
        );
        notifyUnauthorized();
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
            // A feed the assistant logged for the parent is saved to the account's log.
            const logged = loggedFeedingFrom(event);
            if (logged) context.onFeedLogged(logged);
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
