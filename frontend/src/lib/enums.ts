// Controlled vocabularies, mirrored from backend/models/enums.py and
// backend/schemas/tools.py:ActivityLevel (hard rule 2). The values are what the API
// accepts; the labels are what the parent sees. `enums.test.ts` compares the value lists
// to a fixture generated from the backend so drift is caught.

export type Sex = "male" | "female";
export type DietPreference = "omnivore" | "vegetarian" | "pescatarian" | "vegan";
export type Allergen =
  | "milk"
  | "egg"
  | "peanut"
  | "tree_nut"
  | "soy"
  | "wheat"
  | "fish"
  | "shellfish"
  | "sesame";
export type ActivityLevel = "sedentary" | "low_active" | "active" | "very_active";
export type FeedingType = "breastmilk" | "formula" | "solid" | "water";
/** Who a note row comes from; only a doctor's row may change a nutrient target. */
export type NoteKind = "doctor" | "preference";

export interface Option<T extends string> {
  value: T;
  label: string;
}

export const SEX_OPTIONS: readonly Option<Sex>[] = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
];

export const DIET_PREFERENCE_OPTIONS: readonly Option<DietPreference>[] = [
  { value: "omnivore", label: "Omnivore" },
  { value: "vegetarian", label: "Vegetarian" },
  { value: "pescatarian", label: "Pescatarian" },
  { value: "vegan", label: "Vegan" },
];

export const ALLERGEN_OPTIONS: readonly Option<Allergen>[] = [
  { value: "milk", label: "Milk" },
  { value: "egg", label: "Egg" },
  { value: "peanut", label: "Peanut" },
  { value: "tree_nut", label: "Tree nut" },
  { value: "soy", label: "Soy" },
  { value: "wheat", label: "Wheat" },
  { value: "fish", label: "Fish" },
  { value: "shellfish", label: "Shellfish" },
  { value: "sesame", label: "Sesame" },
];

export const ACTIVITY_LEVEL_OPTIONS: readonly Option<ActivityLevel>[] = [
  { value: "sedentary", label: "Sedentary" },
  { value: "low_active", label: "Low active" },
  { value: "active", label: "Active" },
  { value: "very_active", label: "Very active" },
];

export const FEEDING_TYPE_OPTIONS: readonly Option<FeedingType>[] = [
  { value: "breastmilk", label: "Breast milk" },
  { value: "formula", label: "Formula" },
  { value: "solid", label: "Solid food" },
  { value: "water", label: "Water" },
];

export const NUTRIENT_LABELS: Record<string, string> = {
  calories: "calories",
  protein: "protein",
  iron: "iron",
};

export const NOTE_KIND_OPTIONS: readonly Option<NoteKind>[] = [
  { value: "doctor", label: "Doctor's note" },
  { value: "preference", label: "Preference" },
];
