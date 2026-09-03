"use client";

import { ChefHat } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { ChatWidget } from "@/components/chat/chat-widget";
import { ChildContextForm } from "@/components/side-panel/child-context-form";
import { DailyTargets } from "@/components/side-panel/daily-targets";
import { FeedingLogTab } from "@/components/side-panel/feeding-log-tab";
import { GrowthTab } from "@/components/side-panel/growth-tab";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChat, type RequestContext } from "@/hooks/use-chat";
import { useChildContext } from "@/hooks/use-child-context";
import { useFeedingLog } from "@/hooks/use-feeding-log";
import { useGrowthLog } from "@/hooks/use-growth-log";
import { latestNoteOutcomes } from "@/lib/note-outcomes";
import type { CurrentUser, LoggedFeeding } from "@/lib/api-types";
import {
  ADMIN_LINK,
  APP_TITLE,
  CHAT_FEED_NEEDS_CHILD,
  CHAT_FEED_SAVE_FAILED,
  SIGN_OUT,
  TAB_CHILD,
  TAB_GROWTH,
  TAB_LOG,
  TAB_TARGETS,
} from "@/lib/copy";

interface Props {
  user: CurrentUser;
  onSignOut: () => void;
}

export function ChatPage({ user, onSignOut }: Props) {
  const childContext = useChildContext();
  const { childId } = childContext;
  const feedingLog = useFeedingLog(childId);
  const growth = useGrowthLog(childId);
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
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <span className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-full border-[3px] border-ink bg-card text-ink">
            <ChefHat className="size-4" strokeWidth={2.5} />
          </span>
          <h1 className="text-lg leading-none text-tomato">{APP_TITLE}</h1>
        </span>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="truncate" data-testid="account-email">
            {user.email}
          </span>
          {user.is_admin && (
            <Link href="/admin/foods" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              {ADMIN_LINK}
            </Link>
          )}
          <Button type="button" variant="ghost" size="sm" onClick={onSignOut}>
            {SIGN_OUT}
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-2xl flex-1 pb-36">
        <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="gap-0">
          <TabsList className="mx-4 mt-4 w-auto">
            <TabsTrigger value="child">{TAB_CHILD}</TabsTrigger>
            <TabsTrigger value="log">{TAB_LOG}</TabsTrigger>
            <TabsTrigger value="targets">{TAB_TARGETS}</TabsTrigger>
            <TabsTrigger value="growth">{TAB_GROWTH}</TabsTrigger>
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
              saveError={childContext.saveError}
              clearFailed={childContext.clearFailed}
              update={childContext.update}
              save={childContext.save}
              clear={childContext.clear}
              noteOutcomes={latestNoteOutcomes(chat.messages)}
            />
          </TabsContent>
          <TabsContent value="log">
            <FeedingLogTab log={feedingLog} />
          </TabsContent>
          <TabsContent value="targets">
            <DailyTargets childId={childId} dirty={childContext.dirty} />
          </TabsContent>
          <TabsContent value="growth">
            <GrowthTab growth={growth} birthDate={childContext.profile?.birth_date ?? null} />
          </TabsContent>
        </Tabs>
      </main>
      <ChatWidget chat={chat} feedNotice={feedNotice} isAdmin={user.is_admin} />
    </div>
  );
}
