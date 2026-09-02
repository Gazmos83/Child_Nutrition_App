import { describe, expect, it } from "vitest";
import type { GrowthMeasurement } from "../api-types";
import { addMeasurement, formatMeasuredOn, removeMeasurement, sortNewest } from "../growth-log-store";

function measurement(id: string, measured_on: string): GrowthMeasurement {
  return {
    id,
    measured_on,
    age_months: 8,
    age_months_exact: 8.2,
    weight_kg: 8.5,
    height_cm: null,
    assessment: null,
    created_at: "2026-09-02T09:00:00Z",
  };
}

describe("growth log store", () => {
  it("keeps the list newest first and replaces a same-id row", () => {
    const older = measurement("a", "2026-08-01");
    const newer = measurement("b", "2026-09-01");
    const list = addMeasurement(addMeasurement([], older), newer);
    expect(list.map((m) => m.id)).toEqual(["b", "a"]);
    const replaced = addMeasurement(list, { ...older, weight_kg: 9 });
    expect(replaced.map((m) => m.id)).toEqual(["b", "a"]);
    expect(replaced[1].weight_kg).toBe(9);
  });

  it("sorts whatever order the server sent", () => {
    const list = sortNewest([measurement("a", "2026-08-01"), measurement("b", "2026-09-01")]);
    expect(list.map((m) => m.id)).toEqual(["b", "a"]);
  });

  it("removes by id and leaves the rest", () => {
    const list = [measurement("b", "2026-09-01"), measurement("a", "2026-08-01")];
    expect(removeMeasurement(list, "b").map((m) => m.id)).toEqual(["a"]);
    expect(removeMeasurement(list, "zzz")).toHaveLength(2);
  });

  it("formats a day and falls back to the raw string", () => {
    expect(formatMeasuredOn("2026-09-01")).toMatch(/2026/);
    expect(formatMeasuredOn("junk")).toBe("junk");
  });
});
