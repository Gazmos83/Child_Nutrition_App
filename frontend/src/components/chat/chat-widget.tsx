"use client";

import { ChefHat, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import babyChef from "@/assets/baby-chef-5.png";
import { MessageInput } from "@/components/chat/message-input";
import { MessageList } from "@/components/chat/message-list";
import { Button } from "@/components/ui/button";
import type { useChat } from "@/hooks/use-chat";
import { APP_TITLE, CHAT_CLOSE_LABEL, CHAT_OPEN_LABEL } from "@/lib/copy";

interface Props {
  chat: ReturnType<typeof useChat>;
  feedNotice: string | null;
}

/**
 * The floating chef button and the chat panel it opens. The panel stays mounted and is
 * hidden with visibility (not display or unmount) so the draft text and scroll position
 * survive closing; the messages themselves live in `useChat` up in ChatPage either way.
 */
export function ChatWidget({ chat, feedNotice }: Props) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) panelRef.current?.querySelector("textarea")?.focus();
  }, [open]);

  const close = () => {
    setOpen(false);
    launcherRef.current?.focus();
  };

  return (
    <>
      <button
        ref={launcherRef}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-label={open ? CHAT_CLOSE_LABEL : CHAT_OPEN_LABEL}
        data-testid="chat-launcher"
        className="fixed right-4 bottom-4 z-40 w-28 rounded-full outline-none transition-transform drop-shadow-[3px_3px_2px_rgb(0_0_0/0.25)] hover:scale-105 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {/* The badge artwork is die-cut and carries its own outline and banner. */}
        <Image src={babyChef} alt="" aria-hidden="true" className="w-full" />
      </button>
      <div
        ref={panelRef}
        role="dialog"
        aria-label={APP_TITLE}
        data-testid="chat-panel"
        onKeyDown={(e) => {
          if (e.key === "Escape") close();
        }}
        className={`fixed right-4 bottom-36 z-40 flex h-[min(40rem,calc(100dvh-11rem))] w-[min(26rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border-[3px] border-ink bg-card shadow-[6px_8px_0_var(--ink)] transition-[opacity,translate] duration-150 max-sm:right-0 max-sm:bottom-0 max-sm:h-dvh max-sm:w-full max-sm:rounded-none max-sm:border-0 max-sm:shadow-none ${
          open ? "visible opacity-100" : "pointer-events-none invisible translate-y-2 opacity-0"
        }`}
      >
        <header className="flex items-center justify-between gap-2 border-b px-3 py-2">
          <span className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-full border-[3px] border-ink bg-card text-ink">
              <ChefHat className="size-4" strokeWidth={2.5} />
            </span>
            <h2 className="text-lg leading-none text-tomato">{APP_TITLE}</h2>
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={CHAT_CLOSE_LABEL}
            onClick={close}
          >
            <X className="size-4" />
          </Button>
        </header>
        {feedNotice && (
          <p className="border-b bg-muted px-4 py-2 text-sm" role="status" data-testid="feed-notice">
            {feedNotice}
          </p>
        )}
        <MessageList messages={chat.messages} onRetry={chat.retry} retryDisabled={chat.isPending} />
        <MessageInput onSend={chat.send} disabled={chat.isPending} />
      </div>
    </>
  );
}
