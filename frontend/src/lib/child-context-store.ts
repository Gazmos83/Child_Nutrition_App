// The side-panel form state, its validation into a `ChildContext`, and its browser
// persistence (design.md Decision 12). Pure except the three localStorage helpers, which
// swallow storage errors: absence is a valid state.

import type { ChildContext } from "./api-types";
import * as copy from "./copy";
import type { ActivityLevel, Allergen, DietPreference, Sex } from "./enums";

export const CHILD_STORAGE_KEY = "child-nutrition:child-context:v1";

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

function isChildForm(value: unknown): value is ChildForm {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.age_months === "string" &&
    typeof v.weight_kg === "string" &&
    typeof v.sex === "string" &&
    typeof v.height_cm === "string" &&
    typeof v.diet_preference === "string" &&
    Array.isArray(v.allergies) &&
    typeof v.doctors_note === "string" &&
    typeof v.activity_level === "string"
  );
}

export function loadChildForm(storage: Storage | undefined = safeStorage()): ChildForm | null {
  try {
    const raw = storage?.getItem(CHILD_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isChildForm(parsed) ? { ...EMPTY_CHILD_FORM, ...parsed } : null;
  } catch {
    return null;
  }
}

export function saveChildForm(form: ChildForm, storage: Storage | undefined = safeStorage()): void {
  try {
    storage?.setItem(CHILD_STORAGE_KEY, JSON.stringify(form));
  } catch {
    // Storage may be unavailable or full; the form still works for this visit.
  }
}

export function clearChildForm(storage: Storage | undefined = safeStorage()): void {
  try {
    storage?.removeItem(CHILD_STORAGE_KEY);
  } catch {
    // Nothing to clear, or storage unavailable.
  }
}

// -- external store for useSyncExternalStore -----------------------------------------------
//
// React reads the form through a subscribe/snapshot pair instead of an effect that copies
// storage into state. The snapshot is the raw stored string (stable between writes) so
// React can compare by identity; `memory` keeps the form for this visit when storage is
// unavailable.

type Listener = () => void;
const listeners = new Set<Listener>();
let memory: string | null = null;
let storageListenerAttached = false;

function notify(): void {
  for (const listener of listeners) listener();
}

export function subscribeChildForm(listener: Listener): () => void {
  listeners.add(listener);
  if (!storageListenerAttached && typeof window !== "undefined") {
    window.addEventListener("storage", (e) => {
      if (e.key === CHILD_STORAGE_KEY) notify();
    });
    storageListenerAttached = true;
  }
  return () => {
    listeners.delete(listener);
  };
}

export function getChildFormSnapshot(): string | null {
  try {
    const stored = safeStorage()?.getItem(CHILD_STORAGE_KEY) ?? null;
    return stored ?? memory;
  } catch {
    return memory;
  }
}

export function parseChildForm(raw: string | null): ChildForm | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isChildForm(parsed) ? { ...EMPTY_CHILD_FORM, ...parsed } : null;
  } catch {
    return null;
  }
}

export function writeChildForm(form: ChildForm | null): void {
  memory = form ? JSON.stringify(form) : null;
  if (form) saveChildForm(form);
  else clearChildForm();
  notify();
}

function safeStorage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}
