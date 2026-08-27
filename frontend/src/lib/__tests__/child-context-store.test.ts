import { describe, expect, it } from "vitest";
import {
  CHILD_STORAGE_KEY,
  EMPTY_CHILD_FORM,
  loadChildForm,
  saveChildForm,
  toChildContext,
} from "../child-context-store";

const FILLED = { ...EMPTY_CHILD_FORM, age_months: "8", weight_kg: "8.5", sex: "female" as const };

describe("toChildContext", () => {
  it("empty form is empty, not invalid", () => {
    const r = toChildContext(EMPTY_CHILD_FORM);
    expect(r.isEmpty).toBe(true);
    expect(r.child).toBeNull();
    expect(r.errors).toEqual({});
  });

  it("valid form becomes a ChildContext with enum values only", () => {
    const r = toChildContext({ ...FILLED, allergies: ["peanut"], doctors_note: "  " });
    expect(r.child).toEqual({
      age_months: 8,
      weight_kg: 8.5,
      sex: "female",
      height_cm: null,
      diet_preference: "omnivore",
      allergies: ["peanut"],
      doctors_note: null,
      activity_level: "low_active",
    });
  });

  it("rejects age outside 0-60 months, fractional months, and years-like input", () => {
    expect(toChildContext({ ...FILLED, age_months: "61" }).errors.age_months).toBeDefined();
    expect(toChildContext({ ...FILLED, age_months: "8.5" }).errors.age_months).toBeDefined();
    expect(toChildContext({ ...FILLED, age_months: "-1" }).errors.age_months).toBeDefined();
    expect(toChildContext({ ...FILLED, age_months: "0" }).child?.age_months).toBe(0);
  });

  it("requires height from 36 months", () => {
    expect(toChildContext({ ...FILLED, age_months: "36" }).errors.height_cm).toContain("36 months");
    expect(toChildContext({ ...FILLED, age_months: "36", height_cm: "95" }).child?.height_cm).toBe(95);
    expect(toChildContext({ ...FILLED, height_cm: "0" }).errors.height_cm).toBeDefined();
  });

  it("rejects non-positive weight and missing sex", () => {
    expect(toChildContext({ ...FILLED, weight_kg: "0" }).errors.weight_kg).toBeDefined();
    expect(toChildContext({ ...FILLED, sex: "" }).errors.sex).toBeDefined();
  });
});

describe("browser persistence", () => {
  it("round-trips through localStorage and tolerates junk", () => {
    saveChildForm(FILLED);
    expect(loadChildForm()).toEqual(FILLED);
    window.localStorage.setItem(CHILD_STORAGE_KEY, "{not json");
    expect(loadChildForm()).toBeNull();
    window.localStorage.setItem(CHILD_STORAGE_KEY, JSON.stringify({ age_months: 8 }));
    expect(loadChildForm()).toBeNull();
  });

  it("survives a missing storage", () => {
    expect(loadChildForm(undefined)).toBeNull();
    expect(() => saveChildForm(FILLED, undefined)).not.toThrow();
  });
});
