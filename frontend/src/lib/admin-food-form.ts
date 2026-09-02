// The administrator's food form as strings, and its validation into a `FoodWrite`. Pure.
// The four safety questions are tri-state on purpose: "" is "not answered yet", and a food
// cannot be saved until every one is answered (food-table-admin design Decision 8).

import type { FoodItem, FoodWrite } from "./api-types";
import * as copy from "./copy";
import type { Allergen, FoodCategory } from "./enums";

export const FOOD_ID_PATTERN = /^[a-z0-9_]+$/;
export const SOLIDS_MIN_AGE_MONTHS = 6;
export const MAX_AGE_MONTHS = 60;

export type YesNo = "yes" | "no" | "";

export interface FoodForm {
  id: string;
  name: string;
  category: FoodCategory | "";
  serving_size: string;
  serving_unit: string;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbohydrate_g: string;
  iron_mg: string;
  calcium_mg: string;
  allergens: Allergen[];
  choking_hazard: YesNo;
  contains_honey: YesNo;
  commonly_unpasteurized: YesNo;
  min_age_months: string;
  source: string;
  notes: string;
}

export type FoodFormErrors = Partial<Record<keyof FoodForm, string>>;

export const SAFETY_FIELDS = ["choking_hazard", "contains_honey", "commonly_unpasteurized"] as const;
const NUMBER_FIELDS = ["calories", "protein_g", "fat_g", "carbohydrate_g", "iron_mg", "calcium_mg"] as const;

export function emptyFoodForm(): FoodForm {
  return {
    id: "",
    name: "",
    category: "",
    serving_size: "",
    serving_unit: "g",
    calories: "",
    protein_g: "",
    fat_g: "",
    carbohydrate_g: "",
    iron_mg: "",
    calcium_mg: "",
    allergens: [],
    choking_hazard: "",
    contains_honey: "",
    commonly_unpasteurized: "",
    min_age_months: "",
    source: "",
    notes: "",
  };
}

/** A stored food as the form shows it, every answer filled in. */
export function fromFood(food: FoodItem): FoodForm {
  const yesNo = (value: boolean): YesNo => (value ? "yes" : "no");
  return {
    id: food.id,
    name: food.name,
    category: food.category,
    serving_size: String(food.serving_size),
    serving_unit: food.serving_unit,
    calories: String(food.calories),
    protein_g: String(food.protein_g),
    fat_g: String(food.fat_g),
    carbohydrate_g: String(food.carbohydrate_g),
    iron_mg: String(food.iron_mg),
    calcium_mg: String(food.calcium_mg),
    allergens: [...food.allergens],
    choking_hazard: yesNo(food.choking_hazard),
    contains_honey: yesNo(food.contains_honey),
    commonly_unpasteurized: yesNo(food.commonly_unpasteurized),
    min_age_months: String(food.min_age_months),
    source: food.source ?? "",
    notes: food.notes ?? "",
  };
}

export type FoodFormResult = { ok: true; value: FoodWrite } | { ok: false; errors: FoodFormErrors };

/** Validate the form the way the server will; the server stays the authority. */
export function toFoodWrite(form: FoodForm): FoodFormResult {
  const errors: FoodFormErrors = {};
  const id = form.id.trim();
  if (!FOOD_ID_PATTERN.test(id)) errors.id = copy.ADMIN_ERROR_ID;
  if (form.name.trim() === "") errors.name = copy.ADMIN_ERROR_REQUIRED;
  if (form.category === "") errors.category = copy.ADMIN_ERROR_REQUIRED;
  if (form.serving_unit.trim() === "") errors.serving_unit = copy.ADMIN_ERROR_REQUIRED;
  if (form.source.trim() === "") errors.source = copy.ADMIN_ERROR_SOURCE;

  const servingSize = Number(form.serving_size);
  if (form.serving_size.trim() === "" || !Number.isFinite(servingSize) || servingSize <= 0) {
    errors.serving_size = copy.ADMIN_ERROR_POSITIVE;
  }
  const numbers: Partial<Record<(typeof NUMBER_FIELDS)[number], number>> = {};
  for (const field of NUMBER_FIELDS) {
    const value = Number(form[field]);
    if (form[field].trim() === "" || !Number.isFinite(value) || value < 0) {
      errors[field] = copy.ADMIN_ERROR_NON_NEGATIVE;
    } else {
      numbers[field] = value;
    }
  }
  for (const field of SAFETY_FIELDS) {
    if (form[field] === "") errors[field] = copy.ADMIN_SAFETY_REQUIRED;
  }
  const age = Number(form.min_age_months);
  if (form.min_age_months.trim() === "" || !Number.isInteger(age) || age < 0 || age > MAX_AGE_MONTHS) {
    errors.min_age_months = copy.ADMIN_ERROR_AGE;
  } else if (form.category === "milk_feed" ? age !== 0 : age < SOLIDS_MIN_AGE_MONTHS) {
    errors.min_age_months = copy.ADMIN_ERROR_AGE_CATEGORY;
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  const notes = form.notes.trim();
  return {
    ok: true,
    value: {
      id,
      name: form.name.trim(),
      category: form.category as FoodCategory,
      serving_size: servingSize,
      serving_unit: form.serving_unit.trim(),
      calories: numbers.calories!,
      protein_g: numbers.protein_g!,
      fat_g: numbers.fat_g!,
      carbohydrate_g: numbers.carbohydrate_g!,
      iron_mg: numbers.iron_mg!,
      calcium_mg: numbers.calcium_mg!,
      allergens: [...form.allergens],
      choking_hazard: form.choking_hazard === "yes",
      contains_honey: form.contains_honey === "yes",
      commonly_unpasteurized: form.commonly_unpasteurized === "yes",
      min_age_months: age,
      source: form.source.trim(),
      notes: notes === "" ? null : notes,
    },
  };
}
