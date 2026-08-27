// The client-held feeding log (change 2 design Decision 11): pure list operations, a
// localStorage mirror, and the external-store pair React reads it through. Entries are
// `LoggedFeeding`s exactly as the server returned them; nutrients are never computed here.

import type { FeedingEntry, LoggedFeeding, NutrientTotals } from "./api-types";
import { isLoggedFeeding } from "./api-types";

export const FEEDING_LOG_STORAGE_KEY = "child-nutrition:feeding-log:v1";
export const LOG_RETENTION_DAYS = 14;
export const MAX_LOG_ENTRIES = 200;

const DAY_MS = 24 * 60 * 60 * 1000;

/** The calendar day of an instant in an IANA zone, as YYYY-MM-DD. */
export function localDay(iso: string, timeZone: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  } catch {
    return date.toISOString().slice(0, 10);
  }
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function byNewest(a: LoggedFeeding, b: LoggedFeeding): number {
  return b.entry.fed_at.localeCompare(a.entry.fed_at);
}

export function addEntry(log: LoggedFeeding[], logged: LoggedFeeding): LoggedFeeding[] {
  const next = [logged, ...log.filter((e) => e.entry.id !== logged.entry.id)].sort(byNewest);
  return next.slice(0, MAX_LOG_ENTRIES);
}

export function removeEntry(log: LoggedFeeding[], id: string): LoggedFeeding[] {
  return log.filter((e) => e.entry.id !== id);
}

export function pruneOlderThan(
  log: LoggedFeeding[],
  now: Date = new Date(),
  days: number = LOG_RETENTION_DAYS,
): LoggedFeeding[] {
  const cutoff = now.getTime() - days * DAY_MS;
  return log.filter((e) => new Date(e.entry.fed_at).getTime() >= cutoff);
}

export function todayEntries(
  log: LoggedFeeding[],
  timeZone: string,
  now: Date = new Date(),
): LoggedFeeding[] {
  const today = localDay(now.toISOString(), timeZone);
  return log.filter((e) => localDay(e.entry.fed_at, timeZone) === today);
}

export function groupByDay(
  log: LoggedFeeding[],
  timeZone: string,
): { day: string; entries: LoggedFeeding[] }[] {
  const groups = new Map<string, LoggedFeeding[]>();
  for (const e of [...log].sort(byNewest)) {
    const day = localDay(e.entry.fed_at, timeZone);
    groups.set(day, [...(groups.get(day) ?? []), e]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, entries]) => ({ day, entries }));
}

/** Sum of server-returned nutrients, one decimal — display only, never sent anywhere. */
export function sumNutrients(entries: LoggedFeeding[]): NutrientTotals {
  const total: NutrientTotals = {
    calories: 0,
    protein_g: 0,
    fat_g: 0,
    carbohydrate_g: 0,
    iron_mg: 0,
    calcium_mg: 0,
  };
  for (const e of entries) {
    for (const key of Object.keys(total) as (keyof NutrientTotals)[]) {
      total[key] += e.nutrients[key] ?? 0;
    }
  }
  for (const key of Object.keys(total) as (keyof NutrientTotals)[]) {
    total[key] = Math.round(total[key] * 10) / 10;
  }
  return total;
}

/** What travels in `ChatRequest.feeding_log`: the entries, not the priced records. */
export function toRequestEntries(log: LoggedFeeding[]): FeedingEntry[] {
  return log.map((e) => ({
    id: e.entry.id,
    fed_at: e.entry.fed_at,
    feeding_type: e.entry.feeding_type,
    food_id: e.entry.food_id ?? null,
    quantity: e.entry.quantity ?? null,
    unit: e.entry.unit,
  }));
}

export function serialize(log: LoggedFeeding[]): string {
  return JSON.stringify(log);
}

export function deserialize(raw: string | null): LoggedFeeding[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isLoggedFeeding).sort(byNewest) : [];
  } catch {
    return [];
  }
}

// -- external store for useSyncExternalStore (same shape as child-context-store) -----------

type Listener = () => void;
const listeners = new Set<Listener>();
let memory: string | null = null;
let storageListenerAttached = false;

function safeStorage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

function notify(): void {
  for (const listener of listeners) listener();
}

export function subscribeFeedingLog(listener: Listener): () => void {
  listeners.add(listener);
  if (!storageListenerAttached && typeof window !== "undefined") {
    window.addEventListener("storage", (e) => {
      if (e.key === FEEDING_LOG_STORAGE_KEY) notify();
    });
    storageListenerAttached = true;
  }
  return () => {
    listeners.delete(listener);
  };
}

export function getFeedingLogSnapshot(): string | null {
  try {
    return safeStorage()?.getItem(FEEDING_LOG_STORAGE_KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function writeFeedingLog(log: LoggedFeeding[]): void {
  const raw = serialize(log);
  memory = raw;
  try {
    safeStorage()?.setItem(FEEDING_LOG_STORAGE_KEY, raw);
  } catch {
    // Storage unavailable or full; the log still lives for this visit.
  }
  notify();
}

export function currentFeedingLog(): LoggedFeeding[] {
  return pruneOlderThan(deserialize(getFeedingLogSnapshot()));
}

export function appendLoggedFeeding(logged: LoggedFeeding): void {
  writeFeedingLog(addEntry(currentFeedingLog(), logged));
}

export function deleteLoggedFeeding(id: string): void {
  writeFeedingLog(removeEntry(currentFeedingLog(), id));
}
