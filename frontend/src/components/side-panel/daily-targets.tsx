"use client";

import { Badge } from "@/components/ui/badge";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { useDailyTargets } from "@/hooks/use-daily-targets";
import type { GapFlag, NutrientTargetRow, OverrideOutcome } from "@/lib/api-types";
import * as copy from "@/lib/copy";

const FLAG_CLASS: Record<GapFlag, string> = {
  below: "border-amber-400 bg-amber-50 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100",
  adequate: "",
  above: "border-sky-400 bg-sky-50 text-sky-950 dark:bg-sky-950/30 dark:text-sky-100",
};

/** The saved child's daily targets, in server order — never computed or reordered here
 * (chat-ui spec: no nutrient number a parent sees originates in the browser). */
export function DailyTargets({ childId, dirty }: { childId: string | null; dirty: boolean }) {
  const query = useDailyTargets(childId);
  return (
    <section className="space-y-3 p-4" data-testid="daily-targets">
      <h3 className="text-sm font-medium">{copy.TARGETS_TITLE}</h3>
      {childId === null ? (
        <p className="text-sm text-muted-foreground">{copy.TARGETS_NEEDS_CHILD}</p>
      ) : dirty ? (
        // Decision 9: numbers for an unsaved draft would imply the browser computed them.
        <p className="text-sm text-muted-foreground" data-testid="targets-save-first">
          {copy.TARGETS_SAVE_FIRST}
        </p>
      ) : query.isError ? (
        <p className="text-sm text-muted-foreground">{copy.TARGETS_UNAVAILABLE}</p>
      ) : query.isPending ? (
        <p className="text-sm text-muted-foreground">{copy.TARGETS_LOADING}</p>
      ) : (
        <>
          {(query.data.doctor_notes_present || query.data.preferences_present) && (
            <p className="text-sm" data-testid="targets-note-on-file">
              {query.data.doctor_notes_present && query.data.preferences_present
                ? copy.TARGETS_NOTES_ON_FILE
                : query.data.doctor_notes_present
                  ? copy.TARGETS_DOCTOR_NOTE_ON_FILE
                  : copy.TARGETS_PREFERENCES_ON_FILE}
            </p>
          )}
          {query.data.overrides.some((o) => o.source === "doctors_note" && o.conflict) && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm dark:border-blue-900/30 dark:bg-blue-950/20">
              <p className="mb-2 font-medium text-blue-950 dark:text-blue-100">{copy.TARGETS_OVERRIDES_TITLE}</p>
              <ul className="space-y-1">
                {query.data.overrides
                  .filter((o) => o.source === "doctors_note" && o.conflict && o.nutrient)
                  .map((override) => (
                    <OverrideNote key={override.nutrient} override={override} />
                  ))}
              </ul>
            </div>
          )}
          <ul className="space-y-3">
            {query.data.targets.items.map((row) => (
              <TargetRow key={row.nutrient} row={row} />
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">{query.data.disclaimer}</p>
        </>
      )}
    </section>
  );
}

function OverrideNote({ override }: { override: OverrideOutcome }) {
  const unit = override.nutrient === "calories" ? "kcal" : override.nutrient === "protein" ? "g" : "mg";
  return (
    <li className="text-xs text-blue-900 dark:text-blue-100" data-testid="override-note">
      <p>
        <span className="font-medium capitalize">{override.nutrient}:</span>{" "}
        {override.applied_value !== null && override.general_value !== null
          ? copy.overrideApplied(override.nutrient, override.applied_value, override.general_value, unit)
          : override.detail}
      </p>
    </li>
  );
}

function TargetRow({ row }: { row: NutrientTargetRow }) {
  if (row.advisory !== null) {
    return (
      <li className="text-sm" data-testid="target-row" data-kind="advisory">
        <div className="mb-1 font-medium">{row.label}</div>
        <p>{row.advisory}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {copy.advisoryFrom(row.source, row.advisory_source_date ?? "")}
        </p>
      </li>
    );
  }
  return (
    <li className="text-sm" data-testid="target-row" data-kind={row.tracked ? "tracked" : "display-only"}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{row.label}</span>
        {row.tracked ? (
          row.flag && (
            <Badge variant="outline" className={FLAG_CLASS[row.flag]}>
              {copy.FLAG_LABELS[row.flag]}
            </Badge>
          )
        ) : (
          <Badge variant="outline">{copy.TARGETS_DISPLAY_ONLY}</Badge>
        )}
      </div>
      <p className="tabular-nums">
        {row.amount !== null && copy.targetValue(row.amount, row.unit)}
        {row.reference_type && (
          <span className="ml-2 text-xs text-muted-foreground">
            {copy.referenceLine(row.reference_type, row.band)}
          </span>
        )}
      </p>
      {row.tracked && (
        <Progress
          value={Math.min((row.ratio ?? 0) * 100, 100)}
          max={100}
          aria-label={row.label}
          className="mt-1"
        >
          <ProgressTrack>
            <ProgressIndicator />
          </ProgressTrack>
        </Progress>
      )}
      {!row.tracked && row.not_tracked_reason && (
        <p className="mt-1 text-xs text-muted-foreground" data-testid="not-tracked-reason">
          {row.not_tracked_reason}
        </p>
      )}
      {row.display_note && <p className="mt-1 text-xs">{row.display_note}</p>}
      <p className="mt-1 text-xs text-muted-foreground">{row.source}</p>
    </li>
  );
}
