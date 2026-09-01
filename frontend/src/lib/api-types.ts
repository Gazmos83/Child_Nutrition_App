// Wire types mirrored from backend/schemas/{chat,rag,tools,auth,child}.py.

import type { ActivityLevel, Allergen, DietPreference, FeedingType, Sex } from "./enums";

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

/** The wire body (`ChatRequestBody`). The child's details and log are read server-side. */
export interface ChatRequest {
  message: string;
  child_id?: string | null;
  history?: ChatTurn[];
  timezone?: string;
  strategy?: Strategy;
  stream?: boolean;
}

// -- account and children (backend/schemas/auth.py, child.py) -------------------------------

export interface CurrentUser {
  id: string;
  email: string;
}

export interface Credentials {
  email: string;
  password: string;
}

/** `ChildProfileWrite`: field-for-field the context the chat resolves the profile into. */
export type ChildProfileWrite = ChildContext;

export interface ChildProfile extends ChildContext {
  id: string;
  height_cm: number | null;
  doctors_note: string | null;
  doctors_note_recorded_at: string | null;
  created_at: string;
}

// -- feeding log (backend/schemas/tools.py; feeding-log spec) ------------------------------

export type FeedingUnit = "ml" | "g";

export interface FeedingEntry {
  id?: string | null;
  fed_at: string;
  feeding_type: FeedingType;
  food_id?: string | null;
  quantity?: number | null;
  unit: FeedingUnit;
}

export interface LoggedFeeding {
  entry: FeedingEntry & { id: string };
  food_id: string | null;
  food_name: string | null;
  quantified: boolean;
  nutrients: NutrientTotals;
  source: string;
}

export interface FoodSummary {
  id: string;
  name: string;
  category: string;
  serving_size: number;
  serving_unit: string;
  min_age_months: number;
}

export type GapNutrient = "calories" | "protein" | "iron" | "calcium";
export type GapFlag = "below" | "adequate" | "above";
export type GapConfidence = "low" | "medium" | "high";

export interface NutrientGap {
  nutrient: GapNutrient;
  label: string;
  unit: "kcal" | "g" | "mg";
  average: number;
  target: number;
  ratio: number;
  flag: GapFlag;
  target_source: string;
  target_band: string;
}

export interface NutrientGapReport {
  status: "ok" | "insufficient_data";
  confidence: GapConfidence | null;
  directional: boolean;
  days_logged: number;
  window_days: number;
  partial_days: number;
  as_of: string;
  gaps: NutrientGap[];
  targets: NutrientTargets;
  note_extraction: NoteExtraction | null;
  override: OverrideOutcome | null;
}

export interface Adjustment {
  nutrient: GapNutrient;
  action: string;
  confidence: GapConfidence | null;
  window_days: number | null;
  detail: string;
}

export function isNutrientGapReport(value: unknown): value is NutrientGapReport {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    (v.status === "ok" || v.status === "insufficient_data") &&
    Array.isArray(v.gaps) &&
    typeof v.days_logged === "number" &&
    typeof v.as_of === "string"
  );
}

export function isLoggedFeeding(value: unknown): value is LoggedFeeding {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  const entry = v.entry as Record<string, unknown> | undefined;
  return (
    typeof entry === "object" &&
    entry !== null &&
    typeof entry.id === "string" &&
    typeof entry.fed_at === "string" &&
    typeof v.nutrients === "object" &&
    v.nutrients !== null &&
    typeof v.quantified === "boolean"
  );
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

// One row of the ordered day-9 target set. Minimal for now: the side-panel change (6.1)
// completes it (advisories, reasons, display notes) while the three legacy members live.
export interface NutrientTargetRow {
  nutrient: string;
  label: string;
  unit: string;
  amount: number | null;
  band: string;
  source: string;
  tracked: boolean;
}

export interface NutrientTargets {
  calories: CalorieTargetResult;
  protein: ProteinTargetResult;
  iron: IronTargetResult;
  items: NutrientTargetRow[];
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

export type MealPlanOutcome = "plan" | "no_safe_plan" | "targets_met";

export interface MealPlanResult {
  outcome: MealPlanOutcome;
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
  adjustments: Adjustment[];
  already_logged: NutrientTotals | null;
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
    (v.outcome === "plan" || v.outcome === "no_safe_plan" || v.outcome === "targets_met") &&
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
