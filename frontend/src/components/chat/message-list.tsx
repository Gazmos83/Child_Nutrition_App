"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/lib/chat-reducer";
import { CHAT_EMPTY, JUMP_TO_LATEST } from "@/lib/copy";
import { AssistantMessage } from "./assistant-message";

// How close to the bottom (px) still counts as reading the latest message. Within it,
// new tokens keep the view pinned; above it, the parent is reading and we stay put.
const PIN_THRESHOLD = 64;

export function MessageList({
  messages,
  onRetry,
  retryDisabled,
}: {
  messages: ChatMessage[];
  onRetry: (id: string) => void;
  retryDisabled: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const last = messages[messages.length - 1];
  const lastText = last?.role === "assistant" ? last.text : last?.text;
  useEffect(() => {
    if (pinned) endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, lastText, pinned]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center text-muted-foreground">
        <p className="max-w-md text-balance">{CHAT_EMPTY}</p>
      </div>
    );
  }
  return (
    <div
      ref={scrollRef}
      className="flex flex-1 flex-col gap-4 overflow-y-auto p-4"
      role="log"
      aria-live="polite"
      onScroll={() => {
        const el = scrollRef.current;
        if (!el) return;
        setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD);
      }}
    >
      {messages.map((m) =>
        m.role === "user" ? (
          <div key={m.id} className="ml-auto max-w-[80%] rounded-lg bg-primary px-4 py-2 text-primary-foreground">
            <p className="whitespace-pre-wrap">{m.text}</p>
          </div>
        ) : (
          <AssistantMessage key={m.id} message={m} onRetry={onRetry} retryDisabled={retryDisabled} />
        ),
      )}
      {!pinned && (
        <div className="sticky bottom-2 self-center">
          <Button size="sm" variant="outline" className="shadow-md" onClick={() => setPinned(true)}>
            {JUMP_TO_LATEST}
          </Button>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
