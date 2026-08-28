import { describe, expect, it } from "vitest";
import type { LoggedFeeding } from "../api-types";
import {
  addEntry,
  groupByDay,
  localDay,
  pruneOlderThan,
  removeEntry,
  sumNutrients,
  todayEntries,
} from "../feeding-log-store";

function logged(id: string, fedAt: string, calories = 100.5): LoggedFeeding {
  return {
    entry: { id, fed_at: fedAt, feeding_type: "formula", food_id: null, quantity: 150, unit: "ml" },
    food_id: "infant_formula_iron_fortified",
    food_name: "Infant formula",
    quantified: true,
    nutrients: { calories, protein_g: 2.1, fat_g: 5.4, carbohydrate_g: 11.1, iron_mg: 1.8, calcium_mg: 79.5 },
    source: "label",
  };
}

const NOW = new Date("2026-08-27T12:00:00Z");

describe("feeding log store", () => {
  it("adds newest first, dedupes by id, and removes by id", () => {
    let log = addEntry([], logged("a", "2026-08-27T08:00:00Z"));
    log = addEntry(log, logged("b", "2026-08-27T10:00:00Z"));
    log = addEntry(log, logged("a", "2026-08-27T08:00:00Z", 67));
    expect(log.map((e) => e.entry.id)).toEqual(["b", "a"]);
    expect(log[1].nutrients.calories).toBe(67);
    expect(removeEntry(log, "b").map((e) => e.entry.id)).toEqual(["a"]);
  });

  it("prunes entries older than fourteen days", () => {
    const log = [
      logged("fresh", "2026-08-27T08:00:00Z"),
      logged("edge", "2026-08-13T12:00:00Z"),
      logged("old", "2026-08-13T11:59:59Z"),
    ];
    expect(pruneOlderThan(log, NOW).map((e) => e.entry.id)).toEqual(["fresh", "edge"]);
  });

  it("today filtering follows the time zone across midnight", () => {
    const late = logged("late", "2026-08-27T23:30:00Z");
    const now = new Date("2026-08-28T00:30:00Z"); // still the 27th in UTC-anywhere-west; the 28th in Tokyo
    expect(todayEntries([late], "Asia/Tokyo", now).map((e) => e.entry.id)).toEqual(["late"]);
    expect(todayEntries([late], "UTC", now)).toEqual([]);
    expect(localDay("2026-08-27T23:30:00Z", "Asia/Tokyo")).toBe("2026-08-28");
    expect(localDay("2026-08-27T23:30:00Z", "America/New_York")).toBe("2026-08-27");
  });

  it("groups by local day, newest day first", () => {
    const groups = groupByDay(
      [logged("a", "2026-08-26T08:00:00Z"), logged("b", "2026-08-27T08:00:00Z"), logged("c", "2026-08-27T09:00:00Z")],
      "UTC",
    );
    expect(groups.map((g) => g.day)).toEqual(["2026-08-27", "2026-08-26"]);
    expect(groups[0].entries.map((e) => e.entry.id)).toEqual(["c", "b"]);
  });

  it("sums server-returned nutrients to one decimal", () => {
    const totals = sumNutrients([logged("a", "2026-08-27T08:00:00Z"), logged("b", "2026-08-27T09:00:00Z")]);
    expect(totals.calories).toBe(201);
    expect(totals.protein_g).toBe(4.2);
    expect(totals.iron_mg).toBe(3.6);
  });
});
