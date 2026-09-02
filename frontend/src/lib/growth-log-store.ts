// Pure list helpers for the growth log. Measurements are `GrowthMeasurement`s exactly as the
// server returned them — the age and the WHO assessment are never computed here.

import type { GrowthMeasurement } from "./api-types";

function byNewest(a: GrowthMeasurement, b: GrowthMeasurement): number {
  return b.measured_on.localeCompare(a.measured_on) || b.id.localeCompare(a.id);
}

/** Newest measurement first, whatever order the rows arrived in. */
export function sortNewest(list: GrowthMeasurement[]): GrowthMeasurement[] {
  return [...list].sort(byNewest);
}

export function addMeasurement(
  list: GrowthMeasurement[],
  measurement: GrowthMeasurement,
): GrowthMeasurement[] {
  return sortNewest([measurement, ...list.filter((m) => m.id !== measurement.id)]);
}

export function removeMeasurement(list: GrowthMeasurement[], id: string): GrowthMeasurement[] {
  return list.filter((m) => m.id !== id);
}

/** A `YYYY-MM-DD` measurement day for display; the raw string when it is not a date. */
export function formatMeasuredOn(day: string): string {
  const date = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return day;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}
