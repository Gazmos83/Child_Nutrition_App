// The side-panel form state and its validation into a `ChildContext`. Pure. Since Day 6
// the profile is saved to the account (`use-child-context.ts`), not to this browser.

import type { ChildContext, ChildProfile } from "./api-types";
import * as copy from "./copy";
import type { ActivityLevel, Allergen, DietPreference, Sex } from "./enums";

export const HEIGHT_REQUIRED_FROM_MONTHS = 36;
export const MAX_AGE_MONTHS = 60;
export const MAX_WEIGHT_KG = 60;
export const MAX_HEIGHT_CM = 150;
export const MAX_NOTE_CHARS = 4000;

export interface ChildForm {
  age_months: string;
  weight_kg: string;
  sex: Sex | "";
  height_cm: string;
  diet_preference: DietPreference;
  allergies: Allergen[];
  doctors_note: string;
  activity_level: ActivityLevel;
}

export const EMPTY_CHILD_FORM: ChildForm = {
  age_months: "",
  weight_kg: "",
  sex: "",
  height_cm: "",
  diet_preference: "omnivore",
  allergies: [],
  doctors_note: "",
  activity_level: "low_active",
};

export type ChildFormErrors = Partial<Record<keyof ChildForm, string>>;

export interface ChildFormResult {
  child: ChildContext | null;
  errors: ChildFormErrors;
  /** True when the parent has not started filling the form. */
  isEmpty: boolean;
}

export function isFormEmpty(form: ChildForm): boolean {
  return form.age_months === "" && form.weight_kg === "" && form.sex === "";
}

export function toChildContext(form: ChildForm): ChildFormResult {
  const errors: ChildFormErrors = {};
  const isEmpty = isFormEmpty(form);
  if (isEmpty) return { child: null, errors, isEmpty };

  const age = Number(form.age_months);
  if (form.age_months.trim() === "" || !Number.isInteger(age) || age < 0 || age > MAX_AGE_MONTHS) {
    errors.age_months = copy.FORM_ERROR_AGE;
  }
  const weight = Number(form.weight_kg);
  if (form.weight_kg.trim() === "" || !Number.isFinite(weight) || weight <= 0 || weight > MAX_WEIGHT_KG) {
    errors.weight_kg = copy.FORM_ERROR_WEIGHT;
  }
  if (form.sex !== "male" && form.sex !== "female") errors.sex = copy.FORM_ERROR_SEX;

  let height: number | null = null;
  if (form.height_cm.trim() !== "") {
    height = Number(form.height_cm);
    if (!Number.isFinite(height) || height <= 0 || height > MAX_HEIGHT_CM) {
      errors.height_cm = copy.FORM_ERROR_HEIGHT;
    }
  } else if (!errors.age_months && age >= HEIGHT_REQUIRED_FROM_MONTHS) {
    errors.height_cm = copy.FORM_ERROR_HEIGHT_REQUIRED;
  }
  if (form.doctors_note.length > MAX_NOTE_CHARS) errors.doctors_note = copy.FORM_ERROR_NOTE;

  if (Object.keys(errors).length > 0) return { child: null, errors, isEmpty };
  const note = form.doctors_note.trim();
  return {
    child: {
      age_months: age,
      weight_kg: weight,
      sex: form.sex as Sex,
      height_cm: height,
      diet_preference: form.diet_preference,
      allergies: [...form.allergies],
      doctors_note: note === "" ? null : note,
      activity_level: form.activity_level,
    },
    errors,
    isEmpty,
  };
}

/** The stored profile as the form shows it (numbers back to strings, nulls to blanks). */
export function fromProfile(profile: ChildProfile): ChildForm {
  return {
    age_months: String(profile.age_months),
    weight_kg: String(profile.weight_kg),
    sex: profile.sex,
    height_cm: profile.height_cm == null ? "" : String(profile.height_cm),
    diet_preference: profile.diet_preference,
    allergies: [...profile.allergies],
    doctors_note: profile.doctors_note ?? "",
    activity_level: profile.activity_level,
  };
}
