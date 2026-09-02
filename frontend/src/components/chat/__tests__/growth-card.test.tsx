import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GrowthAssessmentResult, GrowthIndicatorResult } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { GrowthCard } from "../growth-card";

function row(overrides: Partial<GrowthIndicatorResult>): GrowthIndicatorResult {
  return {
    indicator: "weight_for_age",
    measurement: 8.5,
    unit: "kg",
    z_score: 0.55,
    percentile: 70.9,
    band: "expected",
    who_label: null,
    reference: { sd2neg: 6.3, median: 7.9, sd2pos: 10.2 },
    ...overrides,
  };
}

const BASE: GrowthAssessmentResult = {
  age_months: 8,
  sex: "female",
  weight_kg: 8.5,
  height_cm: 69,
  indicators: [
    row({}),
    row({ indicator: "length_height_for_age", measurement: 69, unit: "cm", z_score: 0.36, percentile: 64.1, reference: { sd2neg: 63.5, median: 68.7, sd2pos: 74 } }),
    row({ indicator: "weight_for_length_height", z_score: 0.44, percentile: 67, reference: { sd2neg: 6.7, median: 8.2, sd2pos: 10.1 } }),
    row({ indicator: "bmi_for_age", measurement: 17.86, unit: "kg/m²", z_score: 0.42, percentile: 66.3, reference: { sd2neg: 14.7, median: 17.3, sd2pos: 20.2 } }),
  ],
  skipped: [],
  source: "WHO Child Growth Standards (2006)",
  source_url: "https://www.who.int/tools/child-growth-standards/standards",
  note: "Compared by completed month (month 8); the height field is read as recumbent length at this age.",
};

describe("GrowthCard", () => {
  it("renders four computed indicators with percentiles, markers, and references", () => {
    const { container } = render(<GrowthCard result={BASE} />);
    expect(screen.getAllByTestId("growth-row")).toHaveLength(4);
    expect(container.querySelectorAll('[data-slot="progress-track"]')).toHaveLength(4);
    expect(screen.getByText("Weight for age")).toBeInTheDocument();
    expect(screen.getByText(/71st percentile/)).toBeInTheDocument();
    expect(screen.getByText(copy.growthReference(6.3, 7.9, 10.2, "kg"))).toBeInTheDocument();
    expect(screen.getByText(copy.GROWTH_SOURCE_LINE)).toBeInTheDocument();
    expect(screen.getByText(copy.GROWTH_TREND_NOTE)).toBeInTheDocument();
    expect(screen.queryAllByTestId("growth-skipped")).toHaveLength(0);
  });

  it("shows WHO's term plainly on a below row", () => {
    const stunted: GrowthAssessmentResult = {
      ...BASE,
      indicators: [
        row({}),
        row({
          indicator: "length_height_for_age",
          measurement: 64.9,
          unit: "cm",
          z_score: -2.4,
          percentile: 0.4,
          band: "below",
          who_label: "stunted",
          reference: { sd2neg: 66.2, median: 70.6, sd2pos: 75 },
        }),
      ],
    };
    render(<GrowthCard result={stunted} />);
    expect(screen.getByTestId("growth-who-label")).toHaveTextContent(
      copy.growthWhoLabel("stunted"),
    );
    expect(screen.getByText(copy.GROWTH_BAND_LABELS.below)).toBeInTheDocument();
    expect(screen.getByText(/below the 1st percentile/)).toBeInTheDocument();
  });

  it("lists skipped indicators with their reasons when no height was given", () => {
    const reason =
      "We need your child's length or height for this one — add it and we'll place it on the WHO chart";
    const noHeight: GrowthAssessmentResult = {
      ...BASE,
      height_cm: null,
      indicators: [row({})],
      skipped: [
        { indicator: "length_height_for_age", reason },
        { indicator: "weight_for_length_height", reason },
        { indicator: "bmi_for_age", reason },
      ],
    };
    const { container } = render(<GrowthCard result={noHeight} />);
    expect(screen.getAllByTestId("growth-row")).toHaveLength(1);
    expect(screen.getAllByTestId("growth-skipped")).toHaveLength(3);
    expect(screen.getAllByText(reason)).toHaveLength(3);
    // Exactly one track: skipped rows never get a marker.
    expect(container.querySelectorAll('[data-slot="progress-track"]')).toHaveLength(1);
  });
});
