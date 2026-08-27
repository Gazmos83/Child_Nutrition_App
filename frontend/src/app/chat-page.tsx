"use client";

import { useCallback, useState } from "react";
import { MessageInput } from "@/components/chat/message-input";
import { MessageList } from "@/components/chat/message-list";
import { ChildContextForm } from "@/components/side-panel/child-context-form";
import { FeedingLogTab } from "@/components/side-panel/feeding-log-tab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChat, type RequestContext } from "@/hooks/use-chat";
import { useChildContext } from "@/hooks/use-child-context";
import { useFeedingLog } from "@/hooks/use-feeding-log";
import { APP_TITLE, TAB_CHILD, TAB_LOG } from "@/lib/copy";

export function ChatPage() {
  const childContext = useChildContext();
  const feedingLog = useFeedingLog();
  const { child } = childContext;
  const { requestEntries, timeZone } = feedingLog;
  const getContext = useCallback(
    (): RequestContext => ({ child, feeding_log: requestEntries, timezone: timeZone }),
    [child, requestEntries, timeZone],
  );
  const chat = useChat(getContext);
  const [tab, setTab] = useState("child");

  return (
    <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[22rem_1fr]">
      <aside className="border-b md:border-b-0 md:border-r md:overflow-y-auto md:max-h-dvh">
        <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="gap-0">
          <TabsList className="mx-4 mt-4 w-auto">
            <TabsTrigger value="child">{TAB_CHILD}</TabsTrigger>
            <TabsTrigger value="log">{TAB_LOG}</TabsTrigger>
          </TabsList>
          <TabsContent value="child">
            <ChildContextForm
              form={childContext.form}
              errors={childContext.errors}
              isEmpty={childContext.isEmpty}
              hydrated={childContext.hydrated}
              update={childContext.update}
              clear={childContext.clear}
            />
          </TabsContent>
          <TabsContent value="log">
            <FeedingLogTab log={feedingLog} />
          </TabsContent>
        </Tabs>
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
