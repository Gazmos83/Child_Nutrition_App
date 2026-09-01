// Every parent-facing string the UI itself writes (design.md Decision 13).
//
// Tone: warm, unhurried, a little playful for everyday states; warm and direct — what
// happened, what it means, what to do next, no wordplay — for anything touching safety,
// allergies, a doctor's instruction, or an error. Names describe the missing information,
// never the child. Components import from here; `copy.test.ts` snapshots the module and
// fails on long string literals elsewhere.

import type { GapConfidence, GapFlag, OverridableNutrient } from "./api-types";

// -- app ----------------------------------------------------------------------------------

export const APP_TITLE = "Little Gourmant";

// -- empty states --------------------------------------------------------------------------

export const PANEL_EMPTY = "Tell us about your growing gourmet to get started";
export const CHAT_EMPTY =
  "Ask us anything about feeding your little one — what to start with, how much, or what a good day of meals looks like";
export const JUMP_TO_LATEST = "Jump to the latest";

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
export const TOOL_STEP_PENDING = "Working on it…";
export const TOOL_STEP_SKIPPED = "Didn't get to it";

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

/** One line about what a tool did, from its wire args and result; null when the label
 * already says it all. Values arrive untyped, so every read is guarded. */
export function toolSummary(
  name: string,
  args: Record<string, unknown>,
  result: Record<string, unknown> | null,
): string | null {
  switch (name) {
    case "calculate_bmi": {
      const weight = asNumber(args.weight_kg);
      const height = asNumber(args.height_cm);
      return weight !== null && height !== null
        ? `BMI from ${formatNumber(weight)} kg and ${formatNumber(height)} cm`
        : null;
    }
    case "calculate_calorie_target":
    case "calculate_protein_target": {
      const age = asNumber(args.age_months);
      const weight = asNumber(args.weight_kg);
      const nutrient = name === "calculate_calorie_target" ? "calories" : "protein";
      return age !== null && weight !== null
        ? `Daily ${nutrient} for ${formatNumber(age)} months and ${formatNumber(weight)} kg`
        : null;
    }
    case "lookup_food": {
      const id = asText(args.food_id);
      const found = asText(result?.name) ?? (id ? id.replaceAll("_", " ") : null);
      return found ? `Looked up ${found}` : null;
    }
    case "calculate_meal_nutrition": {
      const items = Array.isArray(args.items) ? args.items.length : 0;
      if (items === 0) return null;
      return items === 1 ? "Added up one food" : `Added up ${items} foods`;
    }
    case "generate_meal_plan": {
      const age = asNumber(args.age_months);
      return age !== null ? `A day of meals for ${formatNumber(age)} months` : null;
    }
    case "search_guidelines": {
      const query = asText(args.query);
      return query ? `Searched the guidelines for “${query}”` : "Searched the guidelines";
    }
    case "log_feeding": {
      const fed = asText(result?.food_name);
      return fed ? `Logged ${fed}` : "Logged a feed";
    }
    case "get_daily_nutrition":
      return "Added up today's feeds";
    case "get_remaining_targets":
      return "What's left of today's targets";
    case "detect_nutrient_gaps": {
      const days = asNumber(result?.window_days);
      if (days === null || days <= 0) return "Checked recent days";
      return days === 1 ? "Checked the last day" : `Checked the last ${formatNumber(days)} days`;
    }
    default:
      return null;
  }
}

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
export const FORM_SAVE = "Save details";
export const FORM_SAVING = "Saving…";
export const FORM_SAVED = "Saved to your account";
export const FORM_UNSAVED = "Not saved yet";
export const FORM_SAVE_FAILED = "Those details didn't save. Check them and try again";
export const FORM_CLEAR_CONFIRM =
  "This removes your little one's details and their whole feeding log from your account. Continue?";
export const FORM_CLEAR_FAILED = "Those details didn't clear. Try again in a moment";

// -- chat input ----------------------------------------------------------------------------

export const INPUT_PLACEHOLDER = "Ask about feeding your little one…";
export const SEND = "Send";
export const SENDING = "Thinking…";

// -- account (Day 6; direct: signing in guards a child's health record) --------------------

export const AUTH_TITLE = "Welcome";
export const AUTH_INTRO =
  "Sign in to keep your little one's details and feeding log with your account";
export const AUTH_SIGN_IN = "Sign in";
export const AUTH_CREATE = "Create account";
export const AUTH_EMAIL = "Email";
export const AUTH_PASSWORD = "Password";
export const AUTH_PASSWORD_HINT = "At least 8 characters";
export const AUTH_SWITCH_TO_CREATE = "New here? Create an account";
export const AUTH_SWITCH_TO_SIGN_IN = "Already have an account? Sign in";
export const AUTH_WORKING = "One moment…";
export const AUTH_FAILED = "That didn't go through. Check the details and try again";
export const SIGN_OUT = "Sign out";
export const SESSION_LOADING = "Just a moment…";
export const SESSION_EXPIRED =
  "You've been signed out. Sign in again, then tap retry and we'll pick this up";

// -- disclaimer -----------------------------------------------------------------------------

// Mirrors backend/rag/prompts.py:DISCLAIMER for messages that end before `final` arrives
// (interrupted, failed). Checked against the backend fixture in copy.test.ts.
export const DISCLAIMER_FALLBACK =
  "This is general information from published pediatric nutrition guidelines, not medical advice. Please consult your pediatrician about your child's individual needs.";

// -- tool names ----------------------------------------------------------------------------

export const TOOL_LABELS: Record<string, string> = {
  calculate_bmi: "BMI",
  assess_growth: "Growth check",
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
export const LOG_STORED_HERE = "Saved to your account — we show the last fourteen days";
export const LOG_NEEDS_CHILD = "Save your little one's details first, then log feeds here";
export const LOG_UNAVAILABLE = "We couldn't load the log. Check your connection and try again";
export const LOG_REMOVE_FAILED = "That feed didn't come off the log. Try again in a moment";
export const CHAT_FEED_NEEDS_CHILD =
  "The assistant noted a feed, but it isn't saved — save your little one's details first, then log it from the Feeding log tab";
export const CHAT_FEED_SAVE_FAILED =
  "The assistant noted a feed, but it didn't save to your log. Add it from the Feeding log tab";
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

// -- growth card (day-6-growth-assessment; direct voice — weight status is never a joke) ----

export const GROWTH_TITLE = "How growth measures up";
export const GROWTH_INDICATOR_LABELS: Record<string, string> = {
  weight_for_age: "Weight for age",
  length_height_for_age: "Length/height for age",
  weight_for_length_height: "Weight for length/height",
  bmi_for_age: "BMI for age",
};
export const GROWTH_BAND_LABELS: Record<string, string> = {
  well_below: "Well below the expected range",
  below: "Below the expected range",
  expected: "In the expected range",
  above: "Above the expected range",
  well_above: "Well above the expected range",
};
export const GROWTH_TREND_NOTE =
  "Based on the WHO 2006 growth standards — a reference, not a diagnosis. Preterm birth, birth size, and family background all shift where a healthy child falls. Ask your pediatrician to interpret the trend.";
export const GROWTH_SOURCE_LINE = "Reference: WHO Child Growth Standards (2006)";

export function growthReference(lo: number, median: number, hi: number, unit: string): string {
  return `WHO range for this age and sex: ${formatNumber(lo)}–${formatNumber(hi)} ${unit}, median ${formatNumber(median)}`;
}
export function growthWhoLabel(label: string): string {
  return `WHO's term for this range is “${label}” — one to discuss with your pediatrician`;
}
/** A percentile as parents read it on a chart; the extremes say so rather than rounding to 0 or 100. */
export function ordinal(percentile: number): string {
  const n = Math.round(percentile);
  if (n < 1) return "below the 1st";
  if (n > 99) return "above the 99th";
  const tens = n % 100;
  const suffix =
    tens >= 11 && tens <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th";
  return `${n}${suffix}`;
}

// -- daily targets panel (day 9) -------------------------------------------------------------

export const TARGETS_TITLE = "Daily targets";
export const TARGETS_NEEDS_CHILD =
  "Save your little one's details and their daily targets will appear right here";
export const TARGETS_SAVE_FIRST =
  "Save the details first — targets always come from the saved profile, never a draft";
// Direct: touches a doctor's instruction (hard rule 3 — disclosure, never silence).
export const TARGETS_NOTE_ON_FILE =
  "Your doctor's note is on file. These are the general targets; the note is applied when meal plans are made";
export const TARGETS_UNAVAILABLE =
  "We couldn't load the targets. Check your connection and try again";
export const TARGETS_LOADING = "Fetching the day's targets…";
export const TARGETS_DISPLAY_ONLY = "Shown without a score";
export function targetValue(amount: number, unit: string): string {
  return `${formatNumber(amount)} ${unit} a day`;
}
export function referenceLine(referenceType: string, band: string): string {
  return `${referenceType} · ${band}`;
}
export function advisoryFrom(source: string, year: string): string {
  return `From ${source} (${year})`;
}

// -- marketing (Little Gourmant site) -------------------------------------------------------

export const SITE_WORDMARK = "Little Gourmant";
export const NAV_HOME = "Home";
export const NAV_ABOUT = "About Us";
export const NAV_RECIPES = "Recipes";
export const NAV_CONTACT = "Contact Us";
export const NAV_LOGIN = "Login";

export const SITE_TAGLINE = "Nutrition for little eaters";
export const HERO_TITLE = "Every little bite, a happy little story";
export const HERO_SUBCOPY =
  "Little Gourmant helps you cook, offer and celebrate wholesome food with your baby — warm plans, no worry, plenty of applause.";
export const HERO_CTA = "Start our kitchen";
export const HERO_FLIPBOOK_HOVER_HINT = "Hover to watch the first taste";
export const HERO_FLIPBOOK_PLAYING_HINT = "Yum — keep watching…";

export const FEATURES_TITLE = "A kitchen that cheers along";
export const FEATURES: readonly { title: string; body: string }[] = [
  {
    title: "Tiny tastes, big smiles",
    body: "Age-by-age meal ideas built from real ingredients, ready in minutes on a busy evening.",
  },
  {
    title: "Gentle tracking",
    body: "Log bites, textures and new flavours in a tap and watch patterns appear without pressure.",
  },
  {
    title: "Grown with guidance",
    body: "Dietitian-reviewed milestones that meet your child exactly where they are today.",
  },
];

export const ABOUT_TITLE = "About Us";
export const ABOUT_PARAGRAPHS: readonly string[] = [
  "Little Gourmant began at a kitchen table, with a wobbly high chair and a bowl of carrots. We believe first foods should feel like a warm story rather than a chore — playful, unhurried and full of encouragement.",
  "Our team of parents, cooks and paediatric dietitians turns trusted nutrition guidance into tiny, doable steps for every stage from first spoon to fussy toddler.",
];

export const RECIPES_TITLE = "Little Recipes";
export const RECIPES: readonly { name: string; age: string; time: string }[] = [
  { name: "Sunny Carrot Mash", age: "6+ months", time: "10 min" },
  { name: "Little Broccoli Trees", age: "8+ months", time: "12 min" },
  { name: "Tomato & Lentil Cuddle", age: "10+ months", time: "20 min" },
];

export const CONTACT_TITLE = "Contact Us";
export const CONTACT_INTRO = "Tell us about your little eater — we answer every note within two days.";
export const CONTACT_NAME_PLACEHOLDER = "Your name";
export const CONTACT_EMAIL_PLACEHOLDER = "Email";
export const CONTACT_MESSAGE_PLACEHOLDER = "How can we help?";
export const CONTACT_SUBMIT = "Send a note";

export function footerCopyright(year: number): string {
  return `© ${year} Little Gourmant — made with warm hands.`;
}

// -- helpers -------------------------------------------------------------------------------

export function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
}
