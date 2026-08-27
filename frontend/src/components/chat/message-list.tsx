"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/chat-reducer";
import { CHAT_EMPTY } from "@/lib/copy";
import { AssistantMessage } from "./assistant-message";

export function MessageList({
  messages,
  onRetry,
  retryDisabled,
}: {
  messages: ChatMessage[];
  onRetry: (id: string) => void;
  retryDisabled: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const lastText = last?.role === "assistant" ? last.text : last?.text;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, lastText]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center text-muted-foreground">
        <p className="max-w-md text-balance">{CHAT_EMPTY}</p>
      </div>
    );
  }
  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4" role="log" aria-live="polite">
      {messages.map((m) =>
        m.role === "user" ? (
          <div key={m.id} className="ml-auto max-w-[80%] rounded-lg bg-primary px-4 py-2 text-primary-foreground">
            <p className="whitespace-pre-wrap">{m.text}</p>
          </div>
        ) : (
          <AssistantMessage key={m.id} message={m} onRetry={onRetry} retryDisabled={retryDisabled} />
        ),
      )}
      <div ref={endRef} />
    </div>
  );
}
