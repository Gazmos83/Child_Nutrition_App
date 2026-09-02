// Wire types mirrored from backend/schemas/{chat,rag,tools,auth,child}.py.

import type {
  ActivityLevel,
  Allergen,
  DietPreference,
  FeedingType,
  FoodCategory,
  NoteKind,
  Sex,
} from "./enums";

export type Strategy = "basic" | "advanced";
export type Intent = "rag" | "tool" | "hybrid";
export type ToolStatus = "ok" | "error";

/** One doctor's-note or preference row (child-notes-restrictions). */
export interface NoteRow {
  kind: NoteKind;
  text: string;
}

export interface ChildContext {
  age_months: number;
  weight_kg: number;
  sex: Sex;
  height_cm?: number | null;
  diet_preference: DietPreference;
  allergies: Allergen[];
  notes?: NoteRow[];
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
  /** Listed in ADMIN_EMAILS; may edit the food table (food-table-admin). */
  is_admin: boolean;
}

export interface Credentials {
  email: string;
  password: string;
}

/**
 * `ChildProfileWrite`: the context the chat resolves the profile into, except that age is
 * never written — the profile takes a date of birth (YYYY-MM-DD) and derives the months.
 */
export type ChildProfileWrite = Omit<ChildContext, "age_months"> & { birth_date: string };

export interface ChildProfile extends ChildContext {
  id: string;
  /** YYYY-MM-DD; `age_months` is derived from it server-side as of today. */
  birth_date: string;
  height_cm: number | null;
  notes: ChildNoteRecord[];
  created_at: string;
}

/** A stored note row with its provenance. */
export interface ChildNoteRecord extends NoteRow {
  id: string;
  recorded_at: string;
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
  overrides: OverrideOutcome[] | null;
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

// One row of the ordered day-9 target set (backend NutrientTarget). The three legacy
// members below stay while the compatibility façade lives.
export interface NutrientTargetRow {
  nutrient: string;
  label: string;
  unit: string;
  amount: number | null;
  reference_type: "AI" | "RDA" | "EER" | null;
  band: string;
  source: string;
  upper_limit: number | null;
  tracked: boolean;
  derivation: string;
  per_kg: number | null;
  activity_level: ActivityLevel | null;
  advisory: string | null;
  advisory_source_date: string | null;
  display_note: string;
  not_tracked_reason: string | null;
  intake_average: number | null;
  ratio: number | null;
  flag: GapFlag | null;
}

export interface NutrientTargets {
  calories: CalorieTargetResult;
  protein: ProteinTargetResult;
  iron: IronTargetResult;
  items: NutrientTargetRow[];
}

export interface DailyTargetsResponse {
  targets: NutrientTargets;
  diet_preference: DietPreference;
  doctor_notes_present: boolean;
  preferences_present: boolean;
  disclaimer: string;
}

export interface NutrientCoverage {
  calories: number;
  protein: number;
  iron: number;
}

export interface DoctorsNoteOverride {
  nutrient: OverridableNutrient;
  direction: "max" | "min" | "target";
  value: number;
  unit: "kcal" | "g" | "mg";
}

export interface NoteExtraction {
  status: "not_present" | "applied" | "nothing_to_apply" | "unparsed";
  targets: { note_index: number; override: DoctorsNoteOverride }[];
  avoid: { note_index: number; phrase: string }[];
  issues: { note_index: number; detail: string }[];
  detail: string;
}

/** One avoidance phrase after the server resolved it against the food table. */
export interface Avoidance {
  note_index: number;
  kind: NoteKind;
  phrase: string;
  category: string | null;
  food_ids: string[];
  applied: boolean;
  detail: string;
}

/** What one note row did to the plan, applied or not, with the reason. */
export interface NoteOutcome {
  index: number;
  kind: NoteKind;
  text: string;
  applied: boolean;
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
  overrides: OverrideOutcome[];
  avoidances: Avoidance[];
  note_outcomes: NoteOutcome[];
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
    Array.isArray(v.overrides) &&
    typeof v.message === "string"
  );
}

// -- growth assessment (backend/schemas/tools.py; growth-assessment spec) ------------------

export type GrowthIndicatorKey =
  | "weight_for_age"
  | "length_height_for_age"
  | "weight_for_length_height"
  | "bmi_for_age";

export type GrowthBand = "well_below" | "below" | "expected" | "above" | "well_above";

export interface LmsReference {
  sd2neg: number;
  median: number;
  sd2pos: number;
}

export interface GrowthIndicatorResult {
  indicator: GrowthIndicatorKey;
  measurement: number;
  unit: string;
  z_score: number;
  percentile: number;
  band: GrowthBand;
  who_label: string | null;
  reference: LmsReference;
}

export interface SkippedIndicator {
  indicator: GrowthIndicatorKey;
  reason: string;
}

export interface GrowthAssessmentResult {
  age_months: number;
  sex: Sex;
  weight_kg: number;
  height_cm: number | null;
  indicators: GrowthIndicatorResult[];
  skipped: SkippedIndicator[];
  source: string;
  source_url: string;
  note: string;
}

export function isGrowthAssessmentResult(value: unknown): value is GrowthAssessmentResult {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    Array.isArray(v.indicators) &&
    Array.isArray(v.skipped) &&
    typeof v.note === "string" &&
    typeof v.source === "string" &&
    v.indicators.every(
      (i) => i && typeof i === "object" && "z_score" in (i as Record<string, unknown>),
    )
  );
}

// -- growth log (backend/schemas/child.py; growth-tracking spec) ---------------------------

export interface GrowthMeasurementWrite {
  /** YYYY-MM-DD */
  measured_on: string;
  weight_kg: number;
  height_cm?: number | null;
}

/** A stored measurement with what the server derives on every read. */
export interface GrowthMeasurement {
  id: string;
  measured_on: string;
  /** Completed months on `measured_on`, from the profile's date of birth. */
  age_months: number;
  /** Age on `measured_on` in months to two decimals — for the age axis only. */
  age_months_exact: number;
  weight_kg: number;
  height_cm: number | null;
  /** Null only when the birth date was moved after this measurement was logged. */
  assessment: GrowthAssessmentResult | null;
  created_at: string;
}

// -- growth reference curves (backend/schemas/tools.py; growth-charts) ---------------------

export type CurveXUnit = "months" | "cm";
export type CurveTable = "length" | "height";

export interface GrowthCurve {
  percentile: number;
  /** One value per entry of the set's `xs`. */
  values: number[];
}

export interface GrowthCurveSet {
  indicator: GrowthIndicatorKey;
  x_unit: CurveXUnit;
  /** Which WHO table a centimetre axis shows; null for age axes. */
  x_label_table: CurveTable | null;
  y_unit: string;
  xs: number[];
  curves: GrowthCurve[];
}

export interface GrowthCurvesResponse {
  sex: Sex;
  age_months: number;
  indicators: GrowthCurveSet[];
  source: string;
  source_url: string;
}

// -- food-table administration (backend/schemas/admin.py; food-table-admin) -----------------

/** One food exactly as the table stores it (backend/nutrition/foods.py:FoodItem). */
export interface FoodItem {
  id: string;
  name: string;
  category: FoodCategory;
  serving_size: number;
  serving_unit: string;
  calories: number;
  protein_g: number;
  fat_g: number;
  carbohydrate_g: number;
  iron_mg: number;
  calcium_mg: number;
  /** Optional micronutrients: null means "not measured", distinct from a recorded 0. */
  zinc_mg: number | null;
  vitamin_a_ug: number | null;
  iodine_ug: number | null;
  vitamin_b12_ug: number | null;
  folate_ug: number | null;
  vitamin_c_mg: number | null;
  fiber_g: number | null;
  allergens: Allergen[];
  choking_hazard: boolean;
  contains_honey: boolean;
  commonly_unpasteurized: boolean;
  min_age_months: number;
  source: string | null;
  notes: string | null;
  is_active: boolean;
}

/** The optional micronutrient fields; a blank form field is omitted, meaning "not measured". */
export type Micronutrient =
  | "zinc_mg"
  | "vitamin_a_ug"
  | "iodine_ug"
  | "vitamin_b12_ug"
  | "folate_ug"
  | "vitamin_c_mg"
  | "fiber_g";

/** An administrator's entry: the same shape with the source made mandatory. */
export type FoodWrite = Omit<FoodItem, "source" | "is_active" | "notes" | Micronutrient> & {
  source: string;
  notes?: string | null;
  is_active?: boolean;
} & Partial<Record<Micronutrient, number>>;

export interface FoodTableAdminResponse {
  version: string;
  revision: number;
  source: string;
  foods: FoodItem[];
}

export interface FoodWriteResponse {
  food: FoodItem;
  version: string;
  revision: number;
}

export interface FoodImportRequest {
  format: "yaml" | "csv";
  content: string;
  mode?: "upsert" | "create_only";
  dry_run?: boolean;
}

export interface ImportRowError {
  row: number;
  id: string | null;
  field: string | null;
  message: string;
}

export interface FoodImportResult {
  applied: boolean;
  created: string[];
  updated: string[];
  unchanged: string[];
  errors: ImportRowError[];
  version: string;
  revision: number;
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
