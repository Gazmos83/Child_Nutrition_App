import { describe, expect, it } from "vitest";
import type { FoodItem } from "../api-types";
import { emptyFoodForm, fromFood, toFoodWrite, type FoodForm } from "../admin-food-form";
import * as copy from "../copy";

const LENTILS: FoodItem = {
  id: "lentils_cooked",
  name: "Lentils, cooked",
  category: "legume",
  serving_size: 50,
  serving_unit: "g",
  calories: 58,
  protein_g: 4.5,
  fat_g: 0.2,
  carbohydrate_g: 10,
  iron_mg: 1.7,
  calcium_mg: 9,
  zinc_mg: null,
  vitamin_a_ug: null,
  iodine_ug: null,
  vitamin_b12_ug: null,
  folate_ug: null,
  vitamin_c_mg: null,
  fiber_g: null,
  allergens: [],
  choking_hazard: false,
  contains_honey: false,
  commonly_unpasteurized: false,
  min_age_months: 6,
  source: "USDA FoodData Central FDC 172421",
  notes: null,
  is_active: true,
};

function filled(overrides: Partial<FoodForm> = {}): FoodForm {
  return { ...fromFood(LENTILS), ...overrides };
}

describe("emptyFoodForm", () => {
  it("leaves every safety question unanswered", () => {
    const form = emptyFoodForm();
    expect(form.choking_hazard).toBe("");
    expect(form.contains_honey).toBe("");
    expect(form.commonly_unpasteurized).toBe("");
    expect(form.serving_unit).toBe("g");
  });
});

describe("fromFood", () => {
  it("round-trips a stored food", () => {
    const result = toFoodWrite(fromFood(LENTILS));
    expect(result).toEqual({
      ok: true,
      value: {
        id: "lentils_cooked",
        name: "Lentils, cooked",
        category: "legume",
        serving_size: 50,
        serving_unit: "g",
        calories: 58,
        protein_g: 4.5,
        fat_g: 0.2,
        carbohydrate_g: 10,
        iron_mg: 1.7,
        calcium_mg: 9,
        allergens: [],
        choking_hazard: false,
        contains_honey: false,
        commonly_unpasteurized: false,
        min_age_months: 6,
        source: "USDA FoodData Central FDC 172421",
        notes: null,
      },
    });
  });

  it("shows an empty source and notes as empty strings", () => {
    const form = fromFood({ ...LENTILS, source: null, notes: "soft when mashed" });
    expect(form.source).toBe("");
    expect(form.notes).toBe("soft when mashed");
  });
});

describe("toFoodWrite", () => {
  it("refuses an unanswered safety question, with no default", () => {
    const result = toFoodWrite(filled({ choking_hazard: "" }));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.choking_hazard).toBe(copy.ADMIN_SAFETY_REQUIRED);
      expect(result.errors.contains_honey).toBeUndefined();
    }
  });

  it("requires a source and a well-formed id", () => {
    const result = toFoodWrite(filled({ source: "  ", id: "Kale Chips" }));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.source).toBe(copy.ADMIN_ERROR_SOURCE);
      expect(result.errors.id).toBe(copy.ADMIN_ERROR_ID);
    }
  });

  it("checks the numbers the way the server does", () => {
    const result = toFoodWrite(
      filled({ serving_size: "0", iron_mg: "-1", calories: "abc", min_age_months: "6.5" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.serving_size).toBe(copy.ADMIN_ERROR_POSITIVE);
      expect(result.errors.iron_mg).toBe(copy.ADMIN_ERROR_NON_NEGATIVE);
      expect(result.errors.calories).toBe(copy.ADMIN_ERROR_NON_NEGATIVE);
      expect(result.errors.min_age_months).toBe(copy.ADMIN_ERROR_AGE);
    }
  });

  it("omits blank micronutrients from the write, so they stay not-measured", () => {
    const result = toFoodWrite(filled());
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect("zinc_mg" in result.value).toBe(false);
      expect("fiber_g" in result.value).toBe(false);
    }
  });

  it("sends filled micronutrients, and 0 as a measured zero rather than an omission", () => {
    const result = toFoodWrite(filled({ zinc_mg: "1.3", vitamin_b12_ug: "0" }));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.zinc_mg).toBe(1.3);
      expect(result.value.vitamin_b12_ug).toBe(0);
      expect("folate_ug" in result.value).toBe(false);
    }
  });

  it("refuses a negative or non-numeric micronutrient", () => {
    const result = toFoodWrite(filled({ iodine_ug: "-1", folate_ug: "abc" }));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.iodine_ug).toBe(copy.ADMIN_ERROR_NON_NEGATIVE);
      expect(result.errors.folate_ug).toBe(copy.ADMIN_ERROR_NON_NEGATIVE);
    }
  });

  it("ties the earliest age to the category", () => {
    const solid = toFoodWrite(filled({ min_age_months: "4" }));
    expect(solid.ok).toBe(false);
    if (!solid.ok) expect(solid.errors.min_age_months).toBe(copy.ADMIN_ERROR_AGE_CATEGORY);
    const milk = toFoodWrite(filled({ category: "milk_feed", min_age_months: "6" }));
    expect(milk.ok).toBe(false);
    if (!milk.ok) expect(milk.errors.min_age_months).toBe(copy.ADMIN_ERROR_AGE_CATEGORY);
    expect(toFoodWrite(filled({ category: "milk_feed", min_age_months: "0" })).ok).toBe(true);
  });

  it("trims text, keeps allergens, and turns yes into true", () => {
    const result = toFoodWrite(
      filled({
        name: "  Kale chips ",
        allergens: ["sesame"],
        choking_hazard: "yes",
        notes: "   ",
        source: " Brand label ",
      }),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.name).toBe("Kale chips");
      expect(result.value.allergens).toEqual(["sesame"]);
      expect(result.value.choking_hazard).toBe(true);
      expect(result.value.notes).toBeNull();
      expect(result.value.source).toBe("Brand label");
    }
  });
});
