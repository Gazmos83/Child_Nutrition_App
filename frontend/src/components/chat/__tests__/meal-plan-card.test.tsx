import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MealPlanResult } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { MealPlanCard } from "../meal-plan-card";

const BASE: MealPlanResult = {
  outcome: "plan",
  items: [
    {
      food_id: "breast_milk",
      name: "Breast milk",
      servings: 4,
      serving_size: 100,
      serving_unit: "ml",
      meal: "milk feed",
      reason: "milk feed: about half of daily energy at 6–11 months (WHO)",
    },
    {
      food_id: "infant_cereal_iron_fortified",
      name: "Iron-fortified infant cereal",
      servings: 1,
      serving_size: 30,
      serving_unit: "g",
      meal: "breakfast",
      reason: "grain; highest iron among eligible grain foods",
    },
  ],
  totals: { calories: 620, protein_g: 9.1, fat_g: 20, carbohydrate_g: 70, iron_mg: 10.2, calcium_mg: 300 },
  targets: {
    calories: { calories: 650, band: "7–12 months", formula: "EER", activity_level: null, source: "NIH DRI" },
    protein: { protein_g: 9.4, grams_per_kg: 1.1, reference_type: "RDA", band: "7–12 months", source: "NIH DRI" },
    iron: { iron_mg: 11, reference_type: "RDA", band: "7–12 months", source: "NIH DRI" },
  },
  coverage: { calories: 0.95, protein: 0.97, iron: 0.93 },
  note_extraction: {
    status: "applied",
    override: { nutrient: "calories", direction: "max", value: 650, unit: "kcal" },
    detail: "",
  },
  override: {
    conflict: true,
    source: "doctors_note",
    nutrient: "calories",
    general_value: 743,
    applied_value: 650,
    detail: "note max 650 below general 743",
  },
  exclusions: [
    { food_id: "peanut_butter_thinned", reasons: ["contains a recorded allergen: peanut"] },
    { food_id: "honey", reasons: ["honey is not safe under 12 months (infant botulism)"] },
  ],
  message: "A one-day plan with 1 foods chosen for iron and variety.",
  disclaimer: "This is general information…",
  food_table_version: "2026-08-26.1",
  adjustments: [],
  already_logged: null,
};

describe("MealPlanCard", () => {
  it("shows the doctor's-note banner with both values", () => {
    render(<MealPlanCard plan={BASE} />);
    const banner = screen.getByTestId("override-banner");
    expect(within(banner).getByText(copy.OVERRIDE_TITLE)).toBeInTheDocument();
    expect(banner).toHaveTextContent("650 kcal");
    expect(banner).toHaveTextContent("743 kcal");
    expect(banner).toHaveTextContent("calories");
  });

  it("groups items by slot with servings and shows coverage and exclusions", () => {
    render(<MealPlanCard plan={BASE} />);
    expect(screen.getByText(copy.MEAL_SLOT_LABELS["milk feed"])).toBeInTheDocument();
    expect(screen.getByText(copy.MEAL_SLOT_LABELS.breakfast)).toBeInTheDocument();
    expect(screen.getByText("4 × 100 ml")).toBeInTheDocument();
    expect(screen.getByText("93% of 11 mg")).toBeInTheDocument();
    const exclusions = screen.getByTestId("exclusions");
    expect(exclusions).toHaveTextContent("peanut butter thinned");
    expect(exclusions).toHaveTextContent("infant botulism");
  });

  it("no safe plan shows the headline, both sections, exclusions, and no items", () => {
    const plan: MealPlanResult = {
      ...BASE,
      outcome: "no_safe_plan",
      items: [],
      override: { ...BASE.override, conflict: false, source: "general_target" },
      message: "We couldn't build a safe plan with these details — here's why, and what you might want to check",
    };
    render(<MealPlanCard plan={plan} />);
    expect(screen.getByText(plan.message)).toBeInTheDocument();
    expect(screen.getByText(copy.NO_SAFE_PLAN_WHY)).toBeInTheDocument();
    expect(screen.getByText(copy.NO_SAFE_PLAN_CHECK)).toBeInTheDocument();
    for (const line of copy.NO_SAFE_PLAN_CHECKLIST) expect(screen.getByText(line)).toBeInTheDocument();
    expect(screen.getByTestId("exclusions")).toHaveTextContent("peanut");
    expect(screen.queryByText(copy.PLAN_ITEMS_TITLE)).toBeNull();
    expect(screen.queryByTestId("override-banner")).toBeNull();
  });

  it("shows what the feeding log changed: adjustment and already-logged lines", () => {
    render(
      <MealPlanCard
        plan={{
          ...BASE,
          adjustments: [
            { nutrient: "iron", action: "prioritised", confidence: "medium", window_days: 3, detail: "3-day average 6.2 mg" },
          ],
          already_logged: { calories: 310, protein_g: 8, fat_g: 10, carbohydrate_g: 40, iron_mg: 2.1, calcium_mg: 120 },
        }}
      />,
    );
    expect(screen.getByTestId("adjustment")).toHaveTextContent(copy.adjustedFor("iron", 3));
    expect(screen.getByTestId("already-logged")).toHaveTextContent(copy.alreadyLogged(310, 8, 2.1));
    expect(screen.getByText(copy.PLAN_REST_OF_DAY)).toBeInTheDocument();
    // Coverage is shown against what remained of the day, not the full-day targets.
    expect(screen.getByText("95% of 340 kcal")).toBeInTheDocument();
    expect(screen.getByText("97% of 1.4 g")).toBeInTheDocument();
    expect(screen.getByText("93% of 8.9 mg")).toBeInTheDocument();
  });

  it("targets met: says today is covered, shows the message, and lists no items", () => {
    const message = "Today's already covered — what you've logged meets the day's targets. Nothing more to plan; enjoy the rest of it";
    render(
      <MealPlanCard
        plan={{
          ...BASE,
          outcome: "targets_met",
          items: [],
          message,
          override: { ...BASE.override, conflict: false, source: "general_target" },
          already_logged: { calories: 640, protein_g: 9, fat_g: 20, carbohydrate_g: 70, iron_mg: 10, calcium_mg: 300 },
        }}
      />,
    );
    expect(screen.getByText(copy.PLAN_TARGETS_MET_TITLE)).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByTestId("already-logged")).toHaveTextContent("640 kcal");
    expect(screen.queryByText(copy.PLAN_ITEMS_TITLE)).toBeNull();
    expect(screen.queryByText(copy.PLAN_COVERAGE_TITLE)).toBeNull();
    expect(screen.getByTestId("meal-plan-card")).toHaveAttribute("data-outcome", "targets_met");
  });
});
