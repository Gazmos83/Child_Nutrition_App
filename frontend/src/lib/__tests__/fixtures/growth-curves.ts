// A synthetic, monotonic set of WHO-shaped percentile curves for chart tests. Shapes are
// invented; only the structure (nine ordered curves over shared xs) matters to the UI.

import type { GrowthCurveSet, GrowthCurvesResponse, GrowthIndicatorKey } from "@/lib/api-types";

const PERCENTILES = [10, 20, 30, 40, 50, 60, 70, 80, 90];

function set(
  indicator: GrowthIndicatorKey,
  xs: number[],
  base: number,
  slope: number,
  spread: number,
  yUnit: string,
  table: "length" | "height" | null = null,
): GrowthCurveSet {
  return {
    indicator,
    x_unit: table ? "cm" : "months",
    x_label_table: table,
    y_unit: yUnit,
    xs,
    curves: PERCENTILES.map((percentile) => ({
      percentile,
      values: xs.map((x) => Math.round((base + slope * x + ((percentile - 50) / 40) * spread) * 10) / 10),
    })),
  };
}

const MONTHS = Array.from({ length: 61 }, (_, i) => i);

export function curvesFixture(ageMonths = 7, sex: "female" | "male" = "female"): GrowthCurvesResponse {
  const useHeight = ageMonths >= 24;
  const cms = useHeight
    ? Array.from({ length: 56 }, (_, i) => 65 + i)
    : Array.from({ length: 66 }, (_, i) => 45 + i);
  return {
    sex,
    age_months: ageMonths,
    indicators: [
      set("weight_for_age", MONTHS, 3.2, 0.25, 1.2, "kg"),
      set("length_height_for_age", MONTHS, 49, 1.6, 4, "cm"),
      set("weight_for_length_height", cms, -6, 0.2, 1.2, "kg", useHeight ? "height" : "length"),
      set("bmi_for_age", MONTHS, 13.5, 0.05, 2, "kg/m²"),
    ],
    source: "WHO Child Growth Standards (2006)",
    source_url: "https://www.who.int/tools/child-growth-standards/standards",
  };
}
