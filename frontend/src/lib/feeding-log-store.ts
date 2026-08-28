// Pure list, day, and sum helpers for the feeding log. Entries are `LoggedFeeding`s exactly
// as the server returned them; nutrients are never computed here. Since Day 6 the log is
// saved to the account (`use-feeding-log.ts`), not to this browser.

import type { LoggedFeeding, NutrientTotals } from "./api-types";

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
