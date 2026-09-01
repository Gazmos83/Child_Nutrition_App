import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { NutrientGapReport, NutrientTargetRow } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { GapReportCard } from "../gap-report-card";

function targetRow(overrides: Partial<NutrientTargetRow>): NutrientTargetRow {
  return {
    nutrient: "calories",
    label: "Calories",
    unit: "kcal",
    amount: 678,
    reference_type: "EER",
    band: "7–12 months",
    source: "NIH DRI",
    upper_limit: null,
    tracked: true,
    derivation: "",
    per_kg: null,
    activity_level: null,
    advisory: null,
    advisory_source_date: null,
    display_note: "",
    not_tracked_reason: null,
    intake_average: null,
    ratio: null,
    flag: null,
    ...overrides,
  };
}

const TARGETS: NutrientGapReport["targets"] = {
  calories: { calories: 678, band: "7–12 months", formula: "EER", activity_level: null, source: "NIH DRI" },
  protein: { protein_g: 10.2, grams_per_kg: 1.2, reference_type: "RDA", band: "7–12 months", source: "NIH DRI" },
  iron: { iron_mg: 11, reference_type: "RDA", band: "7–12 months", source: "NIH DRI" },
  items: [
    targetRow({}),
    targetRow({ nutrient: "protein", label: "Protein", unit: "g", amount: 10.2, reference_type: "RDA", per_kg: 1.2 }),
    targetRow({ nutrient: "iron", label: "Iron", unit: "mg", amount: 11, reference_type: "RDA" }),
  ],
};

const INSUFFICIENT: NutrientGapReport = {
  status: "insufficient_data",
  confidence: null,
  directional: false,
  days_logged: 0,
  window_days: 0,
  partial_days: 2,
  as_of: "2026-08-27",
  gaps: [],
  targets: TARGETS,
  note_extraction: null,
  override: null,
};

const MEDIUM_IRON_BELOW: NutrientGapReport = {
  status: "ok",
  confidence: "medium",
  directional: false,
  days_logged: 3,
  window_days: 3,
  partial_days: 1,
  as_of: "2026-08-27",
  gaps: [
    { nutrient: "calories", label: "Calories", unit: "kcal", average: 640, target: 678, ratio: 0.94, flag: "adequate", target_source: "NIH DRI", target_band: "7–12 months" },
    { nutrient: "protein", label: "Protein", unit: "g", average: 9.8, target: 10.2, ratio: 0.96, flag: "adequate", target_source: "NIH DRI", target_band: "7–12 months" },
    { nutrient: "iron", label: "Iron", unit: "mg", average: 6.2, target: 11, ratio: 0.56, flag: "below", target_source: "NIH DRI", target_band: "7–12 months" },
  ],
  targets: TARGETS,
  note_extraction: null,
  override: null,
};

describe("GapReportCard", () => {
  it("insufficient data invites more logging and shows no flags", () => {
    render(<GapReportCard report={INSUFFICIENT} />);
    expect(screen.getByText(copy.GAPS_INSUFFICIENT)).toBeInTheDocument();
    expect(screen.getByTestId("partial-days")).toHaveTextContent(copy.partialDaysNote(2));
    expect(screen.queryAllByTestId("gap-row")).toHaveLength(0);
    expect(screen.queryByTestId("confidence")).toBeNull();
  });

  it("medium iron gap shows confidence, window, the flag, the nudge, and excluded days", () => {
    render(<GapReportCard report={MEDIUM_IRON_BELOW} />);
    expect(screen.getByTestId("confidence")).toHaveTextContent(copy.CONFIDENCE_LABELS.medium);
    expect(screen.getByText(copy.gapsWindow(3, 3))).toBeInTheDocument();
    expect(screen.getByText(copy.FLAG_LABELS.below)).toBeInTheDocument();
    expect(screen.getAllByText(copy.FLAG_LABELS.adequate)).toHaveLength(2);
    expect(screen.getByText(copy.gapLine(6.2, 11, "mg"))).toBeInTheDocument();
    expect(screen.getByText(copy.FLAG_BELOW_NOTE)).toBeInTheDocument();
    expect(screen.getByTestId("partial-days")).toHaveTextContent("1 day had a breastfeed");
    expect(screen.getByText(copy.targetsFrom("NIH DRI", "7–12 months"))).toBeInTheDocument();
    expect(screen.queryByText(copy.GAPS_LOW)).toBeNull();
  });

  it("draws one bar per nutrient, not two", () => {
    const { container } = render(<GapReportCard report={MEDIUM_IRON_BELOW} />);
    expect(container.querySelectorAll('[data-slot="progress-track"]')).toHaveLength(3);
  });

  it("renders a nutrient it has no local name for from the payload's label", () => {
    // Calcium joined the trackable set on day 9; the label rides the payload
    // (design Decision 10), so a new nutrient can never render a blank name.
    const withCalcium: NutrientGapReport = {
      ...MEDIUM_IRON_BELOW,
      gaps: [
        ...MEDIUM_IRON_BELOW.gaps,
        { nutrient: "calcium", label: "Calcium", unit: "mg", average: 210, target: 260, ratio: 0.81, flag: "adequate", target_source: "NIH DRI", target_band: "7–12 months" },
      ],
    };
    const { container } = render(<GapReportCard report={withCalcium} />);
    expect(screen.getByText("Calcium")).toBeInTheDocument();
    expect(screen.getByText(copy.gapLine(210, 260, "mg"))).toBeInTheDocument();
    expect(container.querySelectorAll('[data-slot="progress-track"]')).toHaveLength(4);
  });

  it("low confidence adds the early-look line and the override banner when the note won", () => {
    render(
      <GapReportCard
        report={{
          ...MEDIUM_IRON_BELOW,
          confidence: "low",
          directional: true,
          days_logged: 2,
          window_days: 2,
          partial_days: 0,
          override: {
            conflict: true,
            source: "doctors_note",
            nutrient: "calories",
            general_value: 678,
            applied_value: 650,
            detail: "",
          },
        }}
      />,
    );
    expect(screen.getByText(copy.GAPS_LOW)).toBeInTheDocument();
    expect(screen.getByTestId("override-banner")).toHaveTextContent("650 kcal");
    expect(screen.queryByTestId("partial-days")).toBeNull();
  });
});
