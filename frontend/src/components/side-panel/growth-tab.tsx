"use client";

import { useState } from "react";
import { GrowthIndicatorRow } from "@/components/chat/growth-card";
import { Button } from "@/components/ui/button";
import { type GrowthLogState, useGrowthCurves } from "@/hooks/use-growth-log";
import type { GrowthMeasurement } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { formatMeasuredOn } from "@/lib/growth-log-store";
import { GrowthCharts } from "./growth-charts";
import { LogMeasurementForm } from "./log-measurement-form";

interface Props {
  growth: GrowthLogState;
  /** The saved profile's date of birth, bounding the measurement date. */
  birthDate: string | null;
}

export function GrowthTab({ growth, birthDate }: Props) {
  const [notice, setNotice] = useState<string | null>(null);
  const curves = useGrowthCurves(growth.childId);

  if (growth.childId === null) {
    return (
      <section className="flex flex-col gap-4 p-4" aria-label={copy.GROWTH_LOG_TITLE}>
        <h2 className="text-lg font-semibold">{copy.GROWTH_LOG_TITLE}</h2>
        <p className="rounded-md bg-muted p-3 text-sm" data-testid="growth-needs-child">
          {copy.GROWTH_NEEDS_CHILD}
        </p>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-4 p-4" aria-label={copy.GROWTH_LOG_TITLE}>
      <h2 className="text-lg font-semibold">{copy.GROWTH_LOG_TITLE}</h2>
      <p className="text-xs text-muted-foreground">{copy.GROWTH_STORED_HERE}</p>

      {growth.unavailable && (
        <p className="text-sm text-destructive" role="alert">
          {copy.GROWTH_UNAVAILABLE}
        </p>
      )}
      {growth.hydrated && !growth.unavailable && (
        <>
          <LogMeasurementForm
            birthDate={birthDate}
            submit={growth.add}
            onLogged={() => setNotice(copy.GROWTH_LOGGED)}
          />
          {notice && (
            <p className="text-sm" role="status">
              {notice}
            </p>
          )}
          {growth.removeFailed && (
            <p className="text-sm text-destructive" role="alert">
              {copy.GROWTH_REMOVE_FAILED}
            </p>
          )}
          {growth.measurements.length > 0 && curves.isError && (
            <p className="text-xs text-muted-foreground" data-testid="growth-charts-unavailable">
              {copy.GROWTH_CHARTS_UNAVAILABLE}
            </p>
          )}
          {growth.measurements.length > 0 && curves.data && (
            <GrowthCharts measurements={growth.measurements} curves={curves.data} />
          )}
          {growth.measurements.length === 0 ? (
            <p className="rounded-md bg-muted p-3 text-sm" data-testid="growth-empty">
              {copy.GROWTH_EMPTY}
            </p>
          ) : (
            <ul className="space-y-4" data-testid="growth-entries">
              {growth.measurements.map((measurement) => (
                <MeasurementEntry key={measurement.id} measurement={measurement} onRemove={growth.remove} />
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">{copy.GROWTH_SOURCE_LINE}</p>
          <p className="text-xs text-muted-foreground">{copy.GROWTH_TREND_NOTE}</p>
        </>
      )}
    </section>
  );
}

function MeasurementEntry({
  measurement,
  onRemove,
}: {
  measurement: GrowthMeasurement;
  onRemove: (id: string) => void;
}) {
  const assessment = measurement.assessment;
  return (
    <li className="rounded-md border p-3 text-sm" data-testid="growth-entry">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{formatMeasuredOn(measurement.measured_on)}</span>
        <span className="text-muted-foreground">{copy.monthsOld(measurement.age_months)}</span>
        <span className="tabular-nums">
          {copy.measurementLine(measurement.weight_kg, measurement.height_cm)}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-auto px-1 py-0 text-xs"
          onClick={() => onRemove(measurement.id)}
        >
          {copy.LOG_DELETE}
        </Button>
      </div>
      {assessment === null ? (
        <p className="text-muted-foreground" data-testid="growth-entry-unassessed">
          {copy.GROWTH_ENTRY_UNASSESSED}
        </p>
      ) : (
        <>
          <ul className="space-y-3">
            {assessment.indicators.map((indicator) => (
              <GrowthIndicatorRow key={indicator.indicator} indicator={indicator} />
            ))}
          </ul>
          {measurement.height_cm === null && (
            <p className="mt-2 text-xs text-muted-foreground" data-testid="growth-entry-no-height">
              {copy.GROWTH_ENTRY_NO_HEIGHT}
            </p>
          )}
        </>
      )}
    </li>
  );
}
