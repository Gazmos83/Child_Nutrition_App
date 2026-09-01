"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { FeedingEntry, LoggedFeeding } from "@/lib/api-types";
import { dailyTargetsKey } from "@/hooks/use-daily-targets";
import { fetchJson } from "@/lib/api";
import { addEntry, browserTimeZone, removeEntry, todayEntries } from "@/lib/feeding-log-store";

export function feedingsKey(childId: string | null) {
  return ["feedings", childId] as const;
}

/** The child's feeding log from the account: the last fourteen days, newest first. */
export function useFeedingLog(childId: string | null) {
  const queryClient = useQueryClient();
  const key = feedingsKey(childId);
  const query = useQuery<LoggedFeeding[]>({
    queryKey: key,
    queryFn: () => fetchJson<LoggedFeeding[]>(`/api/children/${childId}/feedings`),
    enabled: childId !== null,
  });
  const timeZone = useMemo(() => browserTimeZone(), []);
  const log = useMemo(() => query.data ?? [], [query.data]);
  const today = useMemo(() => todayEntries(log, timeZone), [log, timeZone]);

  const add = useMutation({
    mutationFn: (entry: FeedingEntry) =>
      fetchJson<LoggedFeeding>(`/api/children/${childId}/feedings`, {
        method: "POST",
        body: entry,
      }),
    onSuccess: (logged) => {
      queryClient.setQueryData<LoggedFeeding[]>(key, (current) => addEntry(current ?? [], logged));
      // The daily-targets panel's tracked rows carry flags computed from this log.
      queryClient.invalidateQueries({ queryKey: dailyTargetsKey(childId) });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`/api/children/${childId}/feedings/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => {
      queryClient.setQueryData<LoggedFeeding[]>(key, (current) => removeEntry(current ?? [], id));
      queryClient.invalidateQueries({ queryKey: dailyTargetsKey(childId) });
    },
  });

  return {
    childId,
    log,
    today,
    timeZone,
    hydrated: childId === null || !query.isPending,
    unavailable: query.isError,
    add: add.mutateAsync,
    remove: remove.mutate,
    removeFailed: remove.isError,
  };
}

export type FeedingLogState = ReturnType<typeof useFeedingLog>;
