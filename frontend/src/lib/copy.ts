// Every parent-facing string the UI itself writes (design.md Decision 13).
//
// Tone: warm, unhurried, a little playful for everyday states; warm and direct — what
// happened, what it means, what to do next, no wordplay — for anything touching safety,
// allergies, a doctor's instruction, or an error. Names describe the missing information,
// never the child. Components import from here; `copy.test.ts` snapshots the module and
// fails on long string literals elsewhere.

import type { GapConfidence, GapFlag, OverridableNutrient } from "./api-types";

// -- app ----------------------------------------------------------------------------------

export const APP_TITLE = "Child Nutrition Assistant";

// -- empty states --------------------------------------------------------------------------

export const PANEL_EMPTY = "Tell us about your growing gourmet to get started";
export const CHAT_EMPTY =
  "Ask us anything about feeding your little one — what to start with, how much, or what a good day of meals looks like";

// -- meal-plan card ------------------------------------------------------------------------

export const OVERRIDE_TITLE = "Your doctor's note takes priority here";

export function overrideBody(
  nutrient: OverridableNutrient | string,
  applied: number,
  general: number,
  unit: string,
): string {
  return `We're using ${formatNumber(applied)} ${unit} instead of the usual ${formatNumber(general)} ${unit} for ${nutrient}, just as your doctor asked`;
}

export const NO_SAFE_PLAN_WHY = "Here's why";
export const NO_SAFE_PLAN_CHECK = "Worth checking";
export const NO_SAFE_PLAN_CHECKLIST: readonly string[] = [
  "Age in months",
  "Recorded allergies",
  "Diet preference",
  "Your pediatrician can suggest foods that fit",
];

export const PLAN_ITEMS_TITLE = "The day's plan";
export const PLAN_COVERAGE_TITLE = "How it lines up with the day's targets";
export const PLAN_EXCLUDED_TITLE = "Left out, and why";
export const PLAN_NO_EXCLUSIONS = "Nothing needed leaving out";

// -- degraded states -----------------------------------------------------------------------

export const INTERRUPTED =
  "The connection dropped partway through. What arrived is above — tap retry and we'll finish the thought";
export const UNREACHABLE = "We couldn't reach the chef. Check your connection and try again";
export function UNAVAILABLE(detail: string): string {
  return `We're not quite set up yet. ${detail}`.trim();
}
export const RETRY = "Retry";

// -- tool activity -------------------------------------------------------------------------

export const TOOL_CHIP_FAILED = "Didn't work out";
export const FROM_PROFILE = "from your child's details";
export const FROM_LOG = "from your feeding log";
export const TOOLS_USED = "What we used";
export const SHOW_DETAILS = "Show details";
export const HIDE_DETAILS = "Hide details";

export const INTENT_LABELS = {
  rag: "From the guidelines",
  tool: "Worked out for your child",
  hybrid: "Guidelines + your child's numbers",
} as const;

// -- sources -------------------------------------------------------------------------------

export const SOURCES_TITLE = "Sources";
export const SHOW_PASSAGE = "Show passage";
export const HIDE_PASSAGE = "Hide passage";

// -- child form ----------------------------------------------------------------------------

export const PANEL_TITLE = "Your little one";
export const FORM_AGE_LABEL = "Age (months)";
export const FORM_AGE_HINT = "Age is in months — 0 to 60 — because the first year moves fast";
export const FORM_WEIGHT_LABEL = "Weight (kg)";
export const FORM_SEX_LABEL = "Sex";
export const FORM_HEIGHT_LABEL = "Height (cm)";
export const FORM_HEIGHT_HINT = "From 36 months we need height too; it's part of the calorie sums";
export const FORM_DIET_LABEL = "Diet preference";
export const FORM_ALLERGIES_LABEL = "Allergies";
export const FORM_NOTE_LABEL = "Doctor's note";
export const FORM_NOTE_HINT =
  "Anything your doctor wrote about calories, protein, or iron — we'll follow it";
export const FORM_ACTIVITY_LABEL = "Activity level";
export const FORM_CLEAR = "Clear details";
export const FORM_SAVED = "Saved in this browser";

// -- chat input ----------------------------------------------------------------------------

export const INPUT_PLACEHOLDER = "Ask about feeding your little one…";
export const SEND = "Send";
export const SENDING = "Thinking…";

// -- disclaimer -----------------------------------------------------------------------------

// Mirrors backend/rag/prompts.py:DISCLAIMER for messages that end before `final` arrives
// (interrupted, failed). Checked against the backend fixture in copy.test.ts.
export const DISCLAIMER_FALLBACK =
  "This is general information from published pediatric nutrition guidelines, not medical advice. Please consult your pediatrician about your child's individual needs.";

// -- tool names ----------------------------------------------------------------------------

export const TOOL_LABELS: Record<string, string> = {
  calculate_bmi: "BMI",
  calculate_calorie_target: "Calorie target",
  calculate_protein_target: "Protein target",
  lookup_food: "Food lookup",
  calculate_meal_nutrition: "Meal nutrition",
  generate_meal_plan: "Meal plan",
  search_guidelines: "Guideline search",
  log_feeding: "Feed logged",
  get_daily_nutrition: "Today's intake",
  get_remaining_targets: "What's left today",
  detect_nutrient_gaps: "Recent-days check",
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replaceAll("_", " ");
}

// -- meal plan card ------------------------------------------------------------------------

export const PLAN_TITLE = "A day of meals";
export const MEAL_SLOT_LABELS: Record<string, string> = {
  "milk feed": "Milk feeds",
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};
export const COVERAGE_LABELS: Record<string, string> = {
  calories: "Calories",
  protein: "Protein",
  iron: "Iron",
};
export function coverageLine(percent: number, target: number, unit: string): string {
  return `${Math.round(percent)}% of ${formatNumber(target)} ${unit}`;
}
export function servingsLine(servings: number, size: number, unit: string): string {
  return `${formatNumber(servings)} × ${formatNumber(size)} ${unit}`;
}

// -- form validation (direct: what is needed, in one line) ---------------------------------

export const FORM_ERROR_AGE = "Age needs to be a whole number of months, from 0 to 60";
export const FORM_ERROR_WEIGHT = "Weight needs to be more than 0 and up to 60 kg";
export const FORM_ERROR_HEIGHT = "Height needs to be more than 0 and up to 150 cm";
export const FORM_ERROR_HEIGHT_REQUIRED = "From 36 months we need a height to work out calories";
export const FORM_ERROR_SEX = "Pick one so the growth references line up";
export const FORM_ERROR_NOTE = "That note is a little long — 4000 characters is the most we can take";

// -- status --------------------------------------------------------------------------------

export const THINKING = "Working on it…";
export const INCOMPLETE = "Incomplete";


// -- feeding log (change 2, design Decision 12) ---------------------------------------------

export const TAB_CHILD = "Child";
export const TAB_LOG = "Feeding log";
export const LOG_TITLE = "Feeding log";
export const LOG_EMPTY =
  "Nothing logged yet. Add a feed whenever you like — the more days we see, the more we can tell you";
export const TODAY_EMPTY = "A blank slate — today's just getting started";
export const LOG_STORED_HERE =
  "Your log lives in this browser for now — fourteen days, then it tidies itself";
export const FEED_LOGGED = "Logged. One more piece of the picture";
export const TODAY_TITLE = "Today so far";
export const LOG_ADD_TITLE = "Log a feed";
export const LOG_TYPE_LABEL = "What";
export const LOG_FOOD_LABEL = "Which food";
export const LOG_QUANTITY_LABEL = "How much";
export const LOG_TIME_LABEL = "When";
export const LOG_ADD = "Add feed";
export const LOG_ADDING = "Adding…";
export const LOG_DELETE = "Remove";
export const LOG_UNMEASURED = "unmeasured";
export const DAY_TODAY = "Today";
export const FORM_QUANTITY_BREASTMILK_HINT =
  "No measure? Leave it blank — we'll count the feed and skip the maths for that day";
export const LOG_ERROR_QUANTITY = "How much needs to be a number above 0";
export const LOG_ERROR_FOOD = "Pick a food from the list";
export const LOG_ERROR_TIME = "Pick a time for this feed";
export const LOG_FOODS_UNAVAILABLE =
  "We couldn't load the food list. Check your connection and try again";
export const LOG_FOODS_LOADING = "Fetching the food list…";
export const LOG_ADD_FAILED = "That feed didn't save. Check the details and try again";

export function todayLine(kcal: number, protein: number, iron: number): string {
  return `${formatNumber(kcal)} kcal · ${formatNumber(protein)} g protein · ${formatNumber(iron)} mg iron`;
}

export function quantityLine(quantity: number | null | undefined, unit: string): string {
  return quantity == null ? LOG_UNMEASURED : `${formatNumber(quantity)} ${unit}`;
}

// -- gap report card -----------------------------------------------------------------------

export const GAPS_TITLE = "How the last few days have gone";
export const GAPS_INSUFFICIENT =
  "We need a few full days of feeds before we can spot patterns. Keep logging and we'll say when we can see enough";
export const GAPS_LOW = "Early days — here's a first look. Take it lightly until there's more to go on";
export function gapsWindow(days: number, window: number): string {
  return `Based on ${days} full ${days === 1 ? "day" : "days"}, looking at the last ${window}`;
}
export function partialDaysNote(n: number): string {
  return `${n} ${n === 1 ? "day" : "days"} had a breastfeed without a measure, so we left them out — that's normal, not a problem`;
}
export const FLAG_LABELS: Record<GapFlag, string> = {
  below: "A little short of target",
  adequate: "On track",
  above: "Above target",
};
export const FLAG_BELOW_NOTE =
  "Averages, not a verdict — one lighter day is fine. This is a nudge toward foods rich in it";
export const CONFIDENCE_LABELS: Record<GapConfidence, string> = {
  low: "Early look",
  medium: "Getting clearer",
  high: "Solid picture",
};
export function gapLine(average: number, target: number, unit: string): string {
  return `${formatNumber(average)} of ${formatNumber(target)} ${unit} a day, on average`;
}
export function targetsFrom(source: string, band: string): string {
  return `Targets from ${source} (${band})`;
}

// -- meal plan card: what the log changed --------------------------------------------------

export function adjustedFor(nutrient: string, days: number | null): string {
  const span = days ? `over the last ${days} ${days === 1 ? "day" : "days"}` : "lately";
  return `Adjusted for ${nutrient} — intake has been a little short ${span}, so we leaned toward ${nutrient}-rich foods`;
}
export function alreadyLogged(kcal: number, protein: number, iron: number): string {
  return `Already logged today: ${todayLine(kcal, protein, iron)}`;
}
export const REMAINING_COVERED = "Covered for today";
export const PLAN_TARGETS_MET_TITLE = "Today's already covered";
export const PLAN_REST_OF_DAY = "The rest of the day";

// -- helpers -------------------------------------------------------------------------------

export function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
}
