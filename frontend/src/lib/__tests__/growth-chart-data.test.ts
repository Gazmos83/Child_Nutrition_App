import { describe, expect, it } from "vitest";
import type { GrowthMeasurement } from "../api-types";
import { ageDomain, niceTicks, pointsFor, xDomainFor, xTicks, yDomain } from "../growth-chart-data";
import { curvesFixture } from "./fixtures/growth-curves";

const WITH_HEIGHT: GrowthMeasurement = {
  id: "m2",
  measured_on: "2026-09-02",
  age_months: 7,
  age_months_exact: 7.7,
  weight_kg: 8.7,
  height_cm: 70,
  assessment: {
    age_months: 7,
    sex: "female",
    weight_kg: 8.7,
    height_cm: 70,
    indicators: [
      { indicator: "weight_for_age", measurement: 8.7, unit: "kg", z_score: 0.5, percentile: 69.1, band: "expected", who_label: null, reference: { sd2neg: 6, median: 7.6, sd2pos: 9.6 } },
      { indicator: "length_height_for_age", measurement: 70, unit: "cm", z_score: 0.9, percentile: 81.6, band: "expected", who_label: null, reference: { sd2neg: 62, median: 67.3, sd2pos: 72 } },
      { indicator: "weight_for_length_height", measurement: 8.7, unit: "kg", z_score: 0.1, percentile: 54, band: "expected", who_label: null, reference: { sd2neg: 7, median: 8.5, sd2pos: 10 } },
      { indicator: "bmi_for_age", measurement: 17.76, unit: "kg/m²", z_score: 0.2, percentile: 57.9, band: "expected", who_label: null, reference: { sd2neg: 14.5, median: 16.8, sd2pos: 19.5 } },
    ],
    skipped: [],
    source: "WHO Child Growth Standards (2006)",
    source_url: "https://www.who.int/",
    note: "",
  },
  created_at: "2026-09-02T09:00:00Z",
};

const WEIGHT_ONLY: GrowthMeasurement = {
  ...WITH_HEIGHT,
  id: "m1",
  measured_on: "2026-08-02",
  age_months: 6,
  age_months_exact: 6.7,
  weight_kg: 8.2,
  height_cm: null,
  assessment: {
    ...WITH_HEIGHT.assessment!,
    height_cm: null,
    indicators: [WITH_HEIGHT.assessment!.indicators[0]],
    skipped: [],
  },
};

describe("growth chart data", () => {
  it("uses WHO's 0-2 and 0-5 year axes by the child's age", () => {
    expect(ageDomain(7)).toEqual([0, 24]);
    expect(ageDomain(23)).toEqual([0, 24]);
    expect(ageDomain(24)).toEqual([0, 60]);
    const curves = curvesFixture(30);
    expect(xDomainFor(curves.indicators[0], 30)).toEqual([0, 60]);
    expect(xDomainFor(curves.indicators[2], 30)).toEqual([65, 120]);
  });

  it("puts every measurement on weight-for-age and only those with height elsewhere", () => {
    const both = [WITH_HEIGHT, WEIGHT_ONLY];
    const wfa = pointsFor("weight_for_age", both);
    expect(wfa.map((p) => [p.x, p.y, p.percentile])).toEqual([
      [6.7, 8.2, 69.1],
      [7.7, 8.7, 69.1],
    ]);
    expect(pointsFor("length_height_for_age", both)).toEqual([
      expect.objectContaining({ id: "m2", x: 7.7, y: 70, unit: "cm", percentile: 81.6 }),
    ]);
    expect(pointsFor("weight_for_length_height", both)).toEqual([
      expect.objectContaining({ id: "m2", x: 70, y: 8.7, unit: "kg", percentile: 54 }),
    ]);
    expect(pointsFor("bmi_for_age", both)).toEqual([
      expect.objectContaining({ id: "m2", x: 7.7, y: 17.76, unit: "kg/m²", percentile: 57.9 }),
    ]);
  });

  it("y domain covers the curves in the x domain and any outlying point", () => {
    const set = curvesFixture(7).indicators[0];
    const [lo, hi] = yDomain(set, [], [0, 24]);
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeGreaterThan(set.curves[8].values[24]);
    const heavy = { ...pointsFor("weight_for_age", [WITH_HEIGHT])[0], y: 40 };
    expect(yDomain(set, [heavy], [0, 24])[1]).toBeGreaterThan(40);
    expect(yDomain({ ...set, xs: [], curves: [] }, [], [0, 24])).toEqual([0, 1]);
  });

  it("ticks are round and axes step sensibly", () => {
    expect(niceTicks(2.1, 12.4)).toEqual([4, 6, 8, 10, 12]);
    expect(niceTicks(0, 1)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(xTicks([0, 24], "months")).toEqual([0, 3, 6, 9, 12, 15, 18, 21, 24]);
    expect(xTicks([0, 60], "months")).toEqual([0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60]);
    expect(xTicks([45, 110], "cm")).toEqual([50, 60, 70, 80, 90, 100, 110]);
  });
});
