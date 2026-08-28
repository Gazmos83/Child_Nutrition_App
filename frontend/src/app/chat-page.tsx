"use client";

import { useCallback, useState } from "react";
import { MessageInput } from "@/components/chat/message-input";
import { MessageList } from "@/components/chat/message-list";
import { ChildContextForm } from "@/components/side-panel/child-context-form";
import { FeedingLogTab } from "@/components/side-panel/feeding-log-tab";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChat, type RequestContext } from "@/hooks/use-chat";
import { useChildContext } from "@/hooks/use-child-context";
import { useFeedingLog } from "@/hooks/use-feeding-log";
import type { CurrentUser, LoggedFeeding } from "@/lib/api-types";
import {
  APP_TITLE,
  CHAT_FEED_NEEDS_CHILD,
  CHAT_FEED_SAVE_FAILED,
  SIGN_OUT,
  TAB_CHILD,
  TAB_LOG,
} from "@/lib/copy";

interface Props {
  user: CurrentUser;
  onSignOut: () => void;
}

export function ChatPage({ user, onSignOut }: Props) {
  const childContext = useChildContext();
  const { childId } = childContext;
  const feedingLog = useFeedingLog(childId);
  const { timeZone, add } = feedingLog;
  const [feedNotice, setFeedNotice] = useState<string | null>(null);
  const onFeedLogged = useCallback(
    (logged: LoggedFeeding) => {
      // Idempotent on the server-assigned id. The answer stands either way; what must not
      // happen is the feed vanishing without a word.
      if (childId === null) {
        setFeedNotice(CHAT_FEED_NEEDS_CHILD);
        return;
      }
      add(logged.entry).then(
        () => setFeedNotice(null),
        () => setFeedNotice(CHAT_FEED_SAVE_FAILED),
      );
    },
    [add, childId],
  );
  const getContext = useCallback(
    (): RequestContext => ({ childId, timezone: timeZone, onFeedLogged }),
    [childId, timeZone, onFeedLogged],
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
              dirty={childContext.dirty}
              saving={childContext.saving}
              saveFailed={childContext.saveFailed}
              clearFailed={childContext.clearFailed}
              update={childContext.update}
              save={childContext.save}
              clear={childContext.clear}
            />
          </TabsContent>
          <TabsContent value="log">
            <FeedingLogTab log={feedingLog} />
          </TabsContent>
        </Tabs>
      </aside>
      <main className="flex max-h-dvh flex-col">
        <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
          <h1 className="text-lg font-semibold">{APP_TITLE}</h1>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="truncate" data-testid="account-email">
              {user.email}
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={onSignOut}>
              {SIGN_OUT}
            </Button>
          </div>
        </header>
        {feedNotice && (
          <p className="border-b bg-muted px-4 py-2 text-sm" role="status" data-testid="feed-notice">
            {feedNotice}
          </p>
        )}
        <MessageList messages={chat.messages} onRetry={chat.retry} retryDisabled={chat.isPending} />
        <MessageInput onSend={chat.send} disabled={chat.isPending} />
      </main>
    </div>
  );
}
