"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import type { LoggedFeeding } from "@/lib/api-types";
import {
  appendLoggedFeeding,
  browserTimeZone,
  deleteLoggedFeeding,
  deserialize,
  getFeedingLogSnapshot,
  pruneOlderThan,
  subscribeFeedingLog,
  todayEntries,
  toRequestEntries,
} from "@/lib/feeding-log-store";

const serverSnapshot = () => null;
const clientReady = () => true;
const serverReady = () => false;

/** The client-held feeding log as an external store; the server renders it empty. */
export function useFeedingLog() {
  const raw = useSyncExternalStore(subscribeFeedingLog, getFeedingLogSnapshot, serverSnapshot);
  const hydrated = useSyncExternalStore(subscribeFeedingLog, clientReady, serverReady);
  const timeZone = useMemo(() => browserTimeZone(), []);
  const log = useMemo(() => pruneOlderThan(deserialize(raw)), [raw]);
  const today = useMemo(() => todayEntries(log, timeZone), [log, timeZone]);
  const requestEntries = useMemo(() => toRequestEntries(log), [log]);
  const add = useCallback((logged: LoggedFeeding) => appendLoggedFeeding(logged), []);
  const remove = useCallback((id: string) => deleteLoggedFeeding(id), []);
  return { log, today, timeZone, hydrated, requestEntries, add, remove };
}

export type FeedingLogState = ReturnType<typeof useFeedingLog>;
