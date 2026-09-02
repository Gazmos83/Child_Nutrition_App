// Pure helpers behind the growth charts: which measurements land on which chart, and the
// axis domains. No number is computed here that the server did not already return — the
// y-values are the stored weight/height or the assessment's own BMI, and a point's
// percentile is the assessment's.

import type { GrowthCurveSet, GrowthIndicatorKey, GrowthMeasurement } from "./api-types";

export interface ChartPoint {
  id: string;
  measured_on: string;
  x: number;
  y: number;
  unit: string;
  percentile: number | null;
}

/** WHO's own chart convention: 0–2 years for the youngest, 0–5 otherwise. */
export function ageDomain(ageMonths: number): [number, number] {
  return ageMonths < 24 ? [0, 24] : [0, 60];
}

export function xDomainFor(set: GrowthCurveSet, ageMonths: number): [number, number] {
  if (set.x_unit === "months") return ageDomain(ageMonths);
  return [set.xs[0], set.xs[set.xs.length - 1]];
}

export function pointsFor(
  indicator: GrowthIndicatorKey,
  measurements: GrowthMeasurement[],
): ChartPoint[] {
  const points: ChartPoint[] = [];
  for (const m of measurements) {
    const assessed = m.assessment?.indicators.find((i) => i.indicator === indicator) ?? null;
    const percentile = assessed?.percentile ?? null;
    const base = { id: m.id, measured_on: m.measured_on, percentile };
    switch (indicator) {
      case "weight_for_age":
        points.push({ ...base, x: m.age_months_exact, y: m.weight_kg, unit: "kg" });
        break;
      case "length_height_for_age":
        if (m.height_cm != null) points.push({ ...base, x: m.age_months_exact, y: m.height_cm, unit: "cm" });
        break;
      case "weight_for_length_height":
        if (m.height_cm != null) points.push({ ...base, x: m.height_cm, y: m.weight_kg, unit: "kg" });
        break;
      case "bmi_for_age":
        if (assessed) points.push({ ...base, x: m.age_months_exact, y: assessed.measurement, unit: assessed.unit });
        break;
    }
  }
  return points.sort((a, b) => a.x - b.x || a.measured_on.localeCompare(b.measured_on));
}

/** Indices of the set's x-values inside the domain. */
export function indicesWithin(set: GrowthCurveSet, domain: [number, number]): number[] {
  return set.xs.map((x, i) => i).filter((i) => set.xs[i] >= domain[0] && set.xs[i] <= domain[1]);
}

/** The curves' span inside the domain, widened to keep every point visible, padded 5%. */
export function yDomain(
  set: GrowthCurveSet,
  points: ChartPoint[],
  xDomain: [number, number],
): [number, number] {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const i of indicesWithin(set, xDomain)) {
    for (const curve of set.curves) {
      min = Math.min(min, curve.values[i]);
      max = Math.max(max, curve.values[i]);
    }
  }
  for (const p of points) {
    min = Math.min(min, p.y);
    max = Math.max(max, p.y);
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  const pad = (max - min) * 0.05 || 1;
  return [Math.max(0, min - pad), max + pad];
}

/** Round tick values at a 1/2/5 step, about `count` of them across the range. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const rough = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalised = rough / magnitude;
  // Snap to the nearest of 1, 2, 5, 10 (thresholds at the geometric midpoints).
  const step = (normalised < 1.5 ? 1 : normalised < 3 ? 2 : normalised < 7 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step / 1000; t += step) {
    ticks.push(Math.round(t * 1000) / 1000);
  }
  return ticks;
}

/** Age axes tick every 3 months to two years and every 6 beyond; centimetre axes every 10. */
export function xTicks(domain: [number, number], unit: "months" | "cm"): number[] {
  const step = unit === "cm" ? 10 : domain[1] <= 24 ? 3 : 6;
  const ticks: number[] = [];
  for (let t = Math.ceil(domain[0] / step) * step; t <= domain[1]; t += step) ticks.push(t);
  return ticks;
}
