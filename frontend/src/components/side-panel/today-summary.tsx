import type { LoggedFeeding } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { sumNutrients } from "@/lib/feeding-log-store";

/** Today's totals, summed from what the server returned for each feed (never computed here). */
export function TodaySummary({ entries }: { entries: LoggedFeeding[] }) {
  const totals = sumNutrients(entries);
  return (
    <div className="rounded-md bg-muted p-3" data-testid="today-summary">
      <h3 className="text-sm font-medium">{copy.TODAY_TITLE}</h3>
      <p className="text-sm tabular-nums">
        {entries.length === 0
          ? copy.TODAY_EMPTY
          : copy.todayLine(totals.calories, totals.protein_g, totals.iron_mg)}
      </p>
    </div>
  );
}
