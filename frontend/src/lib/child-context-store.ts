// The side-panel form state and its validation into a `ChildProfileWrite`. Pure. Since
// Day 6 the profile is saved to the account (`use-child-context.ts`), not to this browser.
// Age is never typed: the form takes a date of birth and the server derives the months;
// `completedMonths` here is the same arithmetic, for the hint and the height rule.

import type { ChildProfile, ChildProfileWrite } from "./api-types";
import * as copy from "./copy";
import type { ActivityLevel, Allergen, DietPreference, Sex } from "./enums";

export const HEIGHT_REQUIRED_FROM_MONTHS = 36;
export const MAX_AGE_MONTHS = 60;
export const MAX_WEIGHT_KG = 60;
export const MAX_HEIGHT_CM = 150;
export const MAX_NOTE_CHARS = 4000;

export interface ChildForm {
  /** YYYY-MM-DD, as a native date input holds it. */
  birth_date: string;
  weight_kg: string;
  sex: Sex | "";
  height_cm: string;
  diet_preference: DietPreference;
  allergies: Allergen[];
  doctors_note: string;
  activity_level: ActivityLevel;
}

export const EMPTY_CHILD_FORM: ChildForm = {
  birth_date: "",
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
  child: ChildProfileWrite | null;
  errors: ChildFormErrors;
  /** True when the parent has not started filling the form. */
  isEmpty: boolean;
}

export function isFormEmpty(form: ChildForm): boolean {
  return form.birth_date === "" && form.weight_kg === "" && form.sex === "";
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** A `YYYY-MM-DD` string as a local calendar date, or null when it is not one. */
export function parseIsoDate(value: string): Date | null {
  const match = ISO_DATE.exec(value.trim());
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(year, month - 1, day);
  const roundTrips =
    date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
  return roundTrips ? date : null;
}

/** Today's local calendar date as `YYYY-MM-DD` (for a date input's `max` and default). */
export function todayIsoDate(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Whole calendar months from a `YYYY-MM-DD` birth date to `today`, or null when the date
 * is malformed or after today. Mirrors backend/nutrition/age.py: a birthday on a day the
 * current month lacks counts as that month's last day.
 */
export function completedMonths(birthDate: string, today: Date = new Date()): number | null {
  const birth = parseIsoDate(birthDate);
  if (!birth) return null;
  const asOf = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (asOf < birth) return null;
  const months = (asOf.getFullYear() - birth.getFullYear()) * 12 + (asOf.getMonth() - birth.getMonth());
  const daysInMonth = new Date(asOf.getFullYear(), asOf.getMonth() + 1, 0).getDate();
  const anniversaryDay = Math.min(birth.getDate(), daysInMonth);
  return asOf.getDate() < anniversaryDay ? months - 1 : months;
}

export function toChildContext(form: ChildForm): ChildFormResult {
  const errors: ChildFormErrors = {};
  const isEmpty = isFormEmpty(form);
  if (isEmpty) return { child: null, errors, isEmpty };

  const age = completedMonths(form.birth_date);
  if (age === null || age > MAX_AGE_MONTHS) errors.birth_date = copy.FORM_ERROR_BIRTH_DATE;
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
  } else if (age !== null && age >= HEIGHT_REQUIRED_FROM_MONTHS) {
    errors.height_cm = copy.FORM_ERROR_HEIGHT_REQUIRED;
  }
  if (form.doctors_note.length > MAX_NOTE_CHARS) errors.doctors_note = copy.FORM_ERROR_NOTE;

  if (Object.keys(errors).length > 0) return { child: null, errors, isEmpty };
  const note = form.doctors_note.trim();
  return {
    child: {
      birth_date: form.birth_date.trim(),
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
    birth_date: profile.birth_date,
    weight_kg: String(profile.weight_kg),
    sex: profile.sex,
    height_cm: profile.height_cm == null ? "" : String(profile.height_cm),
    diet_preference: profile.diet_preference,
    allergies: [...profile.allergies],
    doctors_note: profile.doctors_note ?? "",
    activity_level: profile.activity_level,
  };
}
