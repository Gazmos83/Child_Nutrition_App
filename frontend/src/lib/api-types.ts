// Wire types for POST /api/chat, mirrored from backend/schemas/chat.py, rag.py, tools.py.

import type { ActivityLevel, Allergen, DietPreference, Sex } from "./enums";

export type Strategy = "basic" | "advanced";
export type Intent = "rag" | "tool" | "hybrid";
export type ToolStatus = "ok" | "error";

export interface ChildContext {
  age_months: number;
  weight_kg: number;
  sex: Sex;
  height_cm?: number | null;
  diet_preference: DietPreference;
  allergies: Allergen[];
  doctors_note?: string | null;
  activity_level: ActivityLevel;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  message: string;
  child?: ChildContext | null;
  history?: ChatTurn[];
  strategy?: Strategy;
  stream?: boolean;
}

export interface Citation {
  index: number;
  source: string;
  year: number | null;
  topic: string | null;
  section: string | null;
  document_id: string | null;
  score: number | null;
  excerpt: string;
}

export interface RetrievalMeta {
  strategy: Strategy;
  queries: string[];
  filters: Record<string, unknown>;
  filter_dropped: boolean;
  retrieved: number;
  kept: number;
  top_score: number | null;
}

export interface ToolActivity {
  name: string;
  status: ToolStatus;
  args: Record<string, unknown>;
  used_context: string[];
  result: Record<string, unknown> | null;
  error: string | null;
  detail: string | null;
}

export interface ChatResponse {
  answer: string;
  intent: Intent;
  tools: ToolActivity[];
  citations: Citation[];
  retrieval: RetrievalMeta | null;
  disclaimer: string;
}

// -- meal plan (backend/schemas/tools.py) ---------------------------------------------------

export type MealSlot = "breakfast" | "lunch" | "dinner" | "snack" | "milk feed";
export type OverridableNutrient = "calories" | "protein" | "iron";

export interface PlannedItem {
  food_id: string;
  name: string;
  servings: number;
  serving_size: number;
  serving_unit: string;
  meal: MealSlot;
  reason: string;
}

export interface NutrientTotals {
  calories: number;
  protein_g: number;
  fat_g: number;
  carbohydrate_g: number;
  iron_mg: number;
  calcium_mg: number;
}

export interface CalorieTargetResult {
  calories: number;
  band: string;
  formula: string;
  activity_level: ActivityLevel | null;
  source: string;
}

export interface ProteinTargetResult {
  protein_g: number;
  grams_per_kg: number;
  reference_type: "AI" | "RDA";
  band: string;
  source: string;
}

export interface IronTargetResult {
  iron_mg: number;
  reference_type: "AI" | "RDA";
  band: string;
  source: string;
}

export interface NutrientTargets {
  calories: CalorieTargetResult;
  protein: ProteinTargetResult;
  iron: IronTargetResult;
}

export interface NutrientCoverage {
  calories: number;
  protein: number;
  iron: number;
}

export interface NoteExtraction {
  status: "not_present" | "applied" | "no_numeric_target" | "unparsed";
  override: {
    nutrient: OverridableNutrient;
    direction: "max" | "min" | "target";
    value: number;
    unit: "kcal" | "g" | "mg";
  } | null;
  detail: string;
}

export interface OverrideOutcome {
  conflict: boolean;
  source: "general_target" | "doctors_note";
  nutrient: OverridableNutrient | null;
  general_value: number | null;
  applied_value: number | null;
  detail: string;
}

export interface Exclusion {
  food_id: string;
  reasons: string[];
}

export interface MealPlanResult {
  outcome: "plan" | "no_safe_plan";
  items: PlannedItem[];
  totals: NutrientTotals;
  targets: NutrientTargets;
  coverage: NutrientCoverage;
  note_extraction: NoteExtraction;
  override: OverrideOutcome;
  exclusions: Exclusion[];
  message: string;
  disclaimer: string;
  food_table_version: string;
}

export const UNIT_FOR_NUTRIENT: Record<OverridableNutrient, string> = {
  calories: "kcal",
  protein: "g",
  iron: "mg",
};

export function isMealPlanResult(value: unknown): value is MealPlanResult {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    (v.outcome === "plan" || v.outcome === "no_safe_plan") &&
    Array.isArray(v.items) &&
    typeof v.override === "object" &&
    typeof v.message === "string"
  );
}

// -- server-sent events (design.md Decision 6) --------------------------------------------

export interface RouteEvent {
  event: "route";
  data: { intent: Intent; planned: string[] };
}
export interface ToolEvent {
  event: "tool";
  data: ToolActivity;
}
export interface TokenEvent {
  event: "token";
  data: { text: string };
}
export interface FinalEvent {
  event: "final";
  data: {
    citations: Citation[];
    retrieval: RetrievalMeta | null;
    disclaimer: string;
    intent: Intent;
    tools: { name: string; status: ToolStatus }[];
  };
}
export interface DoneEvent {
  event: "done";
  data: Record<string, never>;
}
export interface ErrorEvent {
  event: "error";
  data: { message: string };
}

export type ChatSseEvent =
  | RouteEvent
  | ToolEvent
  | TokenEvent
  | FinalEvent
  | DoneEvent
  | ErrorEvent;
