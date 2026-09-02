import { describe, expect, it } from "vitest";
import { isGrowthAssessmentResult, isMealPlanResult } from "../api-types";

const GROWTH_FIXTURE = {
  age_months: 8,
  sex: "female",
  weight_kg: 8.5,
  height_cm: 69,
  indicators: [
    {
      indicator: "weight_for_age",
      measurement: 8.5,
      unit: "kg",
      z_score: 0.55,
      percentile: 70.9,
      band: "expected",
      who_label: null,
      reference: { sd2neg: 6.3, median: 7.9, sd2pos: 10.2 },
    },
  ],
  skipped: [],
  source: "WHO Child Growth Standards (2006)",
  source_url: "https://www.who.int/tools/child-growth-standards/standards",
  note: "Compared by completed month (month 8).",
};

const MEAL_PLAN_SHAPE = {
  outcome: "plan",
  items: [],
  overrides: [],
  message: "a day of meals",
};

describe("isGrowthAssessmentResult", () => {
  it("accepts a growth assessment fixture", () => {
    expect(isGrowthAssessmentResult(GROWTH_FIXTURE)).toBe(true);
  });

  it("rejects a meal-plan result and junk", () => {
    expect(isGrowthAssessmentResult(MEAL_PLAN_SHAPE)).toBe(false);
    expect(isGrowthAssessmentResult(null)).toBe(false);
    expect(isGrowthAssessmentResult("growth")).toBe(false);
    expect(isMealPlanResult(GROWTH_FIXTURE)).toBe(false);
  });
});
