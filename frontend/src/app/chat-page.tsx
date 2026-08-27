"use client";

import { useCallback } from "react";
import { MessageInput } from "@/components/chat/message-input";
import { MessageList } from "@/components/chat/message-list";
import { ChildContextForm } from "@/components/side-panel/child-context-form";
import { useChat } from "@/hooks/use-chat";
import { useChildContext } from "@/hooks/use-child-context";
import { APP_TITLE } from "@/lib/copy";

export function ChatPage() {
  const childContext = useChildContext();
  const { child } = childContext;
  const getChild = useCallback(() => child, [child]);
  const chat = useChat(getChild);

  return (
    <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[22rem_1fr]">
      <aside className="border-b md:border-b-0 md:border-r md:overflow-y-auto md:max-h-dvh">
        <ChildContextForm
          form={childContext.form}
          errors={childContext.errors}
          isEmpty={childContext.isEmpty}
          hydrated={childContext.hydrated}
          update={childContext.update}
          clear={childContext.clear}
        />
      </aside>
      <main className="flex max-h-dvh flex-col">
        <header className="border-b px-4 py-3">
          <h1 className="text-lg font-semibold">{APP_TITLE}</h1>
        </header>
        <MessageList messages={chat.messages} onRetry={chat.retry} retryDisabled={chat.isPending} />
        <MessageInput onSend={chat.send} disabled={chat.isPending} />
      </main>
    </div>
  );
}
