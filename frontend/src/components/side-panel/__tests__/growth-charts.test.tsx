import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GrowthMeasurement } from "@/lib/api-types";
import { curvesFixture } from "@/lib/__tests__/fixtures/growth-curves";
import * as copy from "@/lib/copy";
import { GrowthCharts } from "../growth-charts";

const NEWER: GrowthMeasurement = {
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
const OLDER: GrowthMeasurement = {
  ...NEWER,
  id: "m1",
  measured_on: "2026-08-02",
  age_months: 6,
  age_months_exact: 6.7,
  weight_kg: 8.2,
  height_cm: null,
  assessment: { ...NEWER.assessment!, height_cm: null, indicators: [NEWER.assessment!.indicators[0]] },
};

describe("GrowthCharts", () => {
  it("draws four charts with nine curves each, the 50th emphasised", () => {
    render(<GrowthCharts measurements={[NEWER, OLDER]} curves={curvesFixture(7)} />);
    const charts = screen.getAllByTestId("growth-chart");
    expect(charts.map((c) => c.getAttribute("data-indicator"))).toEqual([
      "weight_for_age",
      "length_height_for_age",
      "weight_for_length_height",
      "bmi_for_age",
    ]);
    const curves = screen.getAllByTestId("percentile-curve");
    expect(curves).toHaveLength(36);
    const medians = curves.filter((c) => c.getAttribute("data-percentile") === "50");
    expect(medians).toHaveLength(4);
    for (const median of medians) expect(median.getAttribute("stroke-width")).toBe("2");
    for (const other of curves.filter((c) => !medians.includes(c))) {
      expect(other.getAttribute("stroke-width")).toBe("1");
    }
    for (const chart of charts) {
      const labels = within(chart).getAllByTestId("curve-label").map((l) => l.textContent);
      expect(labels).toEqual(["10th", "50th", "90th"]);
    }
    expect(screen.getByText(copy.GROWTH_CHART_CAPTION)).toBeInTheDocument();
  });

  it("plots the measurements each chart can use", () => {
    render(<GrowthCharts measurements={[NEWER, OLDER]} curves={curvesFixture(7)} />);
    const [wfa, lhfa, wflh, bmi] = screen.getAllByTestId("growth-chart");
    expect(within(wfa).getAllByTestId("chart-point")).toHaveLength(2);
    expect(within(wfa).getByTestId("child-series")).toBeInTheDocument();
    for (const chart of [lhfa, wflh, bmi]) {
      expect(within(chart).getAllByTestId("chart-point")).toHaveLength(1);
      expect(within(chart).queryByTestId("child-series")).toBeNull();
    }
    expect(within(wflh).getByTestId("chart-table-note")).toHaveTextContent(copy.growthTableNote("length"));
    expect(within(wfa).getAllByTestId("x-tick").at(-1)).toHaveTextContent("24");
  });

  it("shows a tooltip with the date and percentile on hover and focus", () => {
    render(<GrowthCharts measurements={[NEWER]} curves={curvesFixture(7)} />);
    const [wfa] = screen.getAllByTestId("growth-chart");
    const point = within(wfa).getByTestId("chart-point");
    expect(point).toHaveAttribute("aria-label", expect.stringContaining("69th percentile"));
    expect(within(wfa).queryByTestId("chart-tooltip")).toBeNull();
    fireEvent.mouseEnter(point);
    expect(within(wfa).getByTestId("chart-tooltip")).toHaveTextContent(/2026.*8\.7 kg, 69th percentile/);
    fireEvent.mouseLeave(point);
    expect(within(wfa).queryByTestId("chart-tooltip")).toBeNull();
    fireEvent.focus(point);
    expect(within(wfa).getByTestId("chart-tooltip")).toBeInTheDocument();
  });

  it("uses the 0-60 month axis and the height table from 24 months", () => {
    const older = { ...NEWER, age_months: 30, age_months_exact: 30.2, height_cm: 92, weight_kg: 13 };
    render(<GrowthCharts measurements={[older]} curves={curvesFixture(30, "male")} />);
    const [wfa, , wflh] = screen.getAllByTestId("growth-chart");
    expect(within(wfa).getAllByTestId("x-tick").at(-1)).toHaveTextContent("60");
    expect(within(wflh).getByTestId("chart-table-note")).toHaveTextContent(copy.growthTableNote("height"));
    expect(wfa.querySelector("svg")).toHaveAttribute("aria-label", copy.chartAriaLabel("Weight for age", "male"));
  });
});
