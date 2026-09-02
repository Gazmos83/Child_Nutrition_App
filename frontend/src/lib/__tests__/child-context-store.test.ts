import { describe, expect, it } from "vitest";
import {
  EMPTY_CHILD_FORM,
  completedMonths,
  fromProfile,
  parseIsoDate,
  toChildContext,
  todayIsoDate,
} from "../child-context-store";
import * as copy from "../copy";

/** A `YYYY-MM-DD` exactly `months` calendar months before `from`, clamped to the month's end. */
function monthsAgo(months: number, from: Date = new Date()): string {
  const year = from.getFullYear();
  const month = from.getMonth() - months;
  const lastDay = new Date(year, month + 1, 0).getDate();
  return todayIsoDate(new Date(year, month, Math.min(from.getDate(), lastDay)));
}

const FILLED = { ...EMPTY_CHILD_FORM, birth_date: monthsAgo(8), weight_kg: "8.5", sex: "female" as const };

describe("completedMonths", () => {
  it("counts whole calendar months, the day before an anniversary excluded", () => {
    expect(completedMonths("2026-01-10", new Date(2026, 4, 9))).toBe(3);
    expect(completedMonths("2026-01-10", new Date(2026, 4, 10))).toBe(4);
    expect(completedMonths("2026-01-10", new Date(2026, 0, 10))).toBe(0);
  });

  it("clamps a month-end birthday to the last day of a shorter month", () => {
    expect(completedMonths("2025-01-31", new Date(2025, 1, 28))).toBe(1);
    expect(completedMonths("2025-01-31", new Date(2025, 2, 30))).toBe(1);
    expect(completedMonths("2025-01-31", new Date(2025, 2, 31))).toBe(2);
  });

  it("is null for a future, malformed, or impossible date", () => {
    expect(completedMonths("2026-05-11", new Date(2026, 4, 10))).toBeNull();
    expect(completedMonths("yesterday", new Date(2026, 4, 10))).toBeNull();
    expect(completedMonths("2026-02-30", new Date(2026, 4, 10))).toBeNull();
    expect(parseIsoDate("2026-02-30")).toBeNull();
  });
});

describe("todayIsoDate", () => {
  it("is the local calendar date, zero-padded", () => {
    expect(todayIsoDate(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("toChildContext", () => {
  it("empty form is empty, not invalid", () => {
    const r = toChildContext(EMPTY_CHILD_FORM);
    expect(r.isEmpty).toBe(true);
    expect(r.child).toBeNull();
    expect(r.errors).toEqual({});
  });

  it("valid form becomes a ChildProfileWrite with a birth date and no typed age", () => {
    const r = toChildContext({ ...FILLED, allergies: ["peanut"], doctors_note: "  " });
    expect(r.child).toEqual({
      birth_date: FILLED.birth_date,
      weight_kg: 8.5,
      sex: "female",
      height_cm: null,
      diet_preference: "omnivore",
      allergies: ["peanut"],
      doctors_note: null,
      activity_level: "low_active",
    });
    expect(r.child).not.toHaveProperty("age_months");
  });

  it("rejects a birth date in the future, past 60 months, or malformed", () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    for (const birth_date of [todayIsoDate(tomorrow), monthsAgo(61), "8", "2026-13-01"]) {
      expect(toChildContext({ ...FILLED, birth_date }).errors.birth_date).toBe(copy.FORM_ERROR_BIRTH_DATE);
    }
    expect(toChildContext({ ...FILLED, birth_date: todayIsoDate() }).child?.birth_date).toBe(todayIsoDate());
    expect(toChildContext({ ...FILLED, birth_date: monthsAgo(60) }).errors.birth_date).toBeUndefined();
  });

  it("requires height from 36 months of derived age", () => {
    expect(toChildContext({ ...FILLED, birth_date: monthsAgo(36) }).errors.height_cm).toContain("36 months");
    expect(toChildContext({ ...FILLED, birth_date: monthsAgo(36), height_cm: "95" }).child?.height_cm).toBe(95);
    expect(toChildContext({ ...FILLED, birth_date: monthsAgo(35) }).errors.height_cm).toBeUndefined();
    expect(toChildContext({ ...FILLED, height_cm: "0" }).errors.height_cm).toBeDefined();
  });

  it("rejects non-positive weight and missing sex", () => {
    expect(toChildContext({ ...FILLED, weight_kg: "0" }).errors.weight_kg).toBeDefined();
    expect(toChildContext({ ...FILLED, sex: "" }).errors.sex).toBeDefined();
  });
});

describe("fromProfile", () => {
  it("shows the stored profile as form strings, blanks for nulls", () => {
    const form = fromProfile({
      id: "c1",
      birth_date: FILLED.birth_date,
      age_months: 8,
      weight_kg: 8.5,
      sex: "female",
      height_cm: null,
      diet_preference: "omnivore",
      allergies: ["peanut"],
      doctors_note: null,
      doctors_note_recorded_at: null,
      activity_level: "low_active",
      created_at: "2026-08-28T09:00:00Z",
    });
    expect(form).toEqual({ ...FILLED, allergies: ["peanut"] });
    // And back again without loss.
    expect(toChildContext(form).child).toEqual({
      birth_date: FILLED.birth_date,
      weight_kg: 8.5,
      sex: "female",
      height_cm: null,
      diet_preference: "omnivore",
      allergies: ["peanut"],
      doctors_note: null,
      activity_level: "low_active",
    });
  });
});
