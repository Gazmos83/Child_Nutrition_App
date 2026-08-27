"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { FeedingLogState } from "@/hooks/use-feeding-log";
import { useFoods } from "@/hooks/use-foods";
import type { LoggedFeeding } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { FEEDING_TYPE_OPTIONS } from "@/lib/enums";
import { groupByDay, localDay } from "@/lib/feeding-log-store";
import { LogFeedForm } from "./log-feed-form";
import { TodaySummary } from "./today-summary";

export function FeedingLogTab({ log }: { log: FeedingLogState }) {
  const foods = useFoods();
  const [notice, setNotice] = useState<string | null>(null);
  const groups = groupByDay(log.log, log.timeZone);
  const today = localDay(new Date().toISOString(), log.timeZone);

  return (
    <section className="flex flex-col gap-4 p-4" aria-label={copy.LOG_TITLE}>
      <h2 className="text-lg font-semibold">{copy.LOG_TITLE}</h2>
      <p className="text-xs text-muted-foreground">{copy.LOG_STORED_HERE}</p>

      {log.hydrated && (
        <>
          <TodaySummary entries={log.today} />
          <LogFeedForm
            foods={foods.data}
            foodsLoading={foods.isPending}
            foodsError={foods.isError}
            onLogged={(logged) => {
              log.add(logged);
              setNotice(copy.FEED_LOGGED);
            }}
          />
          {notice && (
            <p className="text-sm" role="status">
              {notice}
            </p>
          )}
          {log.log.length === 0 ? (
            <p className="rounded-md bg-muted p-3 text-sm" data-testid="log-empty">
              {copy.LOG_EMPTY}
            </p>
          ) : (
            <ul className="space-y-3" data-testid="log-days">
              {groups.map((group) => (
                <li key={group.day}>
                  <h3 className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                    {group.day === today ? copy.DAY_TODAY : formatDay(group.day)}
                  </h3>
                  <ul className="space-y-1">
                    {group.entries.map((entry) => (
                      <EntryRow key={entry.entry.id} entry={entry} timeZone={log.timeZone} onRemove={log.remove} />
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function formatDay(day: string): string {
  const date = new Date(`${day}T12:00:00Z`);
  return Number.isNaN(date.getTime())
    ? day
    : new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(date);
}

function formatTime(iso: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZone }).format(new Date(iso));
  } catch {
    return iso.slice(11, 16);
  }
}

function EntryRow({
  entry,
  timeZone,
  onRemove,
}: {
  entry: LoggedFeeding;
  timeZone: string;
  onRemove: (id: string) => void;
}) {
  const typeLabel = FEEDING_TYPE_OPTIONS.find((o) => o.value === entry.entry.feeding_type)?.label ?? entry.entry.feeding_type;
  return (
    <li className="flex items-baseline justify-between gap-2 text-sm" data-testid="log-entry">
      <span className="tabular-nums text-muted-foreground">{formatTime(entry.entry.fed_at, timeZone)}</span>
      <span className="flex-1 truncate">{entry.food_name ?? typeLabel}</span>
      <span className="tabular-nums text-muted-foreground">
        {copy.quantityLine(entry.entry.quantity, entry.entry.unit)} · {copy.formatNumber(entry.nutrients.calories)} kcal
      </span>
      <Button type="button" variant="ghost" size="sm" className="h-auto px-1 py-0 text-xs" onClick={() => onRemove(entry.entry.id)}>
        {copy.LOG_DELETE}
      </Button>
    </li>
  );
}
