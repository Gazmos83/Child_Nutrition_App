import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import backend from "./fixtures/backend-enums.json";
import * as copy from "../copy";

const EXPORTED: unknown[] = Object.values(copy);
const RENDERED: string[] = [
  ...EXPORTED.flatMap((v) =>
    typeof v === "string" ? [v] : Array.isArray(v) ? v.filter((x) => typeof x === "string") : [],
  ),
  ...Object.values(copy.INTENT_LABELS),
  ...Object.values(copy.GROWTH_INDICATOR_LABELS),
  ...Object.values(copy.GROWTH_BAND_LABELS),
  copy.overrideBody("iron", 8, 11, "mg"),
  copy.UNAVAILABLE("OPENROUTER_API_KEY is not set."),
  copy.growthReference(6.3, 7.9, 10.2, "kg"),
  copy.growthWhoLabel("stunted"),
  copy.ordinal(50),
  copy.ordinal(0.4),
  copy.ordinal(99.8),
  copy.monthsOld(1),
  copy.monthsOld(8),
  copy.measurementLine(8.5, 69),
  copy.measurementLine(8.5, null),
  copy.noteNotApplied("no such food"),
  copy.quoted("no pork"),
  copy.growthTableNote("length"),
  copy.growthTableNote("height"),
  copy.percentileLabel(50),
  copy.chartPointLabel("Sep 2, 2026", 6.9, "kg", 22.3),
  copy.chartPointLabel("Sep 2, 2026", 6.9, "kg", null),
  copy.chartAriaLabel("Weight for age", "female"),
  ...[
    copy.toolSummary("calculate_bmi", { weight_kg: 8.4, height_cm: 68 }, null),
    copy.toolSummary("calculate_calorie_target", { age_months: 8, weight_kg: 8.4 }, null),
    copy.toolSummary("calculate_protein_target", { age_months: 8, weight_kg: 8.4 }, null),
    copy.toolSummary("lookup_food", { food_id: "oatmeal_porridge" }, null),
    copy.toolSummary(
      "lookup_food",
      { food_id: "sweet potato", quantity: 20, unit: "g" },
      { name: "Sweet potato, cooked and mashed" },
    ),
    copy.toolSummary("calculate_meal_nutrition", { items: [{}, {}] }, null),
    copy.toolSummary("calculate_meal_nutrition", { items: [{}] }, null),
    copy.toolSummary("generate_meal_plan", { age_months: 8 }, null),
    copy.toolSummary("search_guidelines", { query: "starting solids" }, null),
    copy.toolSummary("search_guidelines", {}, null),
    copy.toolSummary("log_feeding", {}, { food_name: "oatmeal porridge" }),
    copy.toolSummary("log_feeding", {}, null),
    copy.toolSummary("get_daily_nutrition", {}, null),
    copy.toolSummary("get_remaining_targets", {}, null),
    copy.toolSummary("detect_nutrient_gaps", {}, { window_days: 5 }),
    copy.toolSummary("detect_nutrient_gaps", {}, { window_days: 1 }),
    copy.toolSummary("detect_nutrient_gaps", {}, null),
  ].filter((line): line is string => line !== null),
];

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      return entry === "ui" || entry === "__tests__" ? [] : tsxFiles(full);
    }
    return full.endsWith(".tsx") && !full.endsWith(".test.tsx") ? [full] : [];
  });
}

describe("product copy", () => {
  it("is reviewed as one snapshot", () => {
    expect(copy).toMatchSnapshot();
  });

  it("has no exclamation marks and never reads as a missing child", () => {
    for (const text of RENDERED) {
      expect(text.trim().length).toBeGreaterThan(0);
      expect(text).not.toContain("!");
      expect(text.toLowerCase()).not.toContain("missing child");
    }
    for (const key of Object.keys(copy)) {
      expect(key.toLowerCase()).not.toContain("missing_child_hint");
    }
  });

  it("disclaimer fallback matches the backend verbatim", () => {
    expect(copy.DISCLAIMER_FALLBACK).toBe(backend.disclaimer);
  });

  it("growth trend note names the standard's known limits", () => {
    expect(copy.GROWTH_TREND_NOTE.toLowerCase()).toContain("preterm birth");
    expect(copy.GROWTH_TREND_NOTE).toContain("birth size");
    expect(copy.GROWTH_TREND_NOTE).toContain("pediatrician");
    expect(copy.GROWTH_TREND_NOTE).toContain("not a diagnosis");
  });

  it("percentile ordinals read the way a chart does", () => {
    expect(copy.ordinal(50)).toBe("50th");
    expect(copy.ordinal(62.4)).toBe("62nd");
    expect(copy.ordinal(11)).toBe("11th");
    expect(copy.ordinal(3.2)).toBe("3rd");
    expect(copy.ordinal(0.4)).toBe("below the 1st");
    expect(copy.ordinal(99.9)).toBe("above the 99th");
  });

  it("override body names both values", () => {
    expect(copy.overrideBody("iron", 8, 11, "mg")).toBe(
      "We're using 8 mg instead of the usual 11 mg for iron, just as your doctor asked",
    );
    expect(copy.overrideBody("calories", 650, 743, "kcal")).toContain("650 kcal");
  });

  it("no long JSX text literal lives outside copy.ts", () => {
    const roots = ["src/components", "src/app"].map((p) => path.resolve(process.cwd(), p));
    const offenders: string[] = [];
    for (const root of roots) {
      let files: string[] = [];
      try {
        files = tsxFiles(root);
      } catch {
        continue;
      }
      for (const file of files) {
        const source = readFileSync(file, "utf8");
        // Prose between tags, e.g. `<p>Some long sentence here</p>`. Only letters,
        // spaces and sentence punctuation count, so code between `=>` and `<` is ignored.
        for (const match of source.matchAll(/>\s*([^<>{}\n]{25,})\s*</g)) {
          const text = match[1].trim();
          if (/^[A-Za-z][A-Za-z ,.'’—-]{24,}$/.test(text) && text.includes(" ")) {
            offenders.push(`${path.relative(process.cwd(), file)}: "${text}"`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
