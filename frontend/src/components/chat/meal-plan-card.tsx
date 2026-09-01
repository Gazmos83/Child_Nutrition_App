import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import {
  UNIT_FOR_NUTRIENT,
  type MealPlanResult,
  type MealSlot,
  type OverrideOutcome,
  type PlannedItem,
} from "@/lib/api-types";
import * as copy from "@/lib/copy";

const SLOT_ORDER: MealSlot[] = ["milk feed", "breakfast", "lunch", "dinner", "snack"];

export function MealPlanCard({ plan }: { plan: MealPlanResult }) {
  const noSafePlan = plan.outcome === "no_safe_plan";
  const targetsMet = plan.outcome === "targets_met";
  const title = noSafePlan ? plan.message : targetsMet ? copy.PLAN_TARGETS_MET_TITLE : copy.PLAN_TITLE;
  return (
    <Card className="ink-outline mt-3" data-testid="meal-plan-card" data-outcome={plan.outcome}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {!noSafePlan && <p className="text-sm text-muted-foreground">{plan.message}</p>}
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {plan.override.conflict && <OverrideBanner override={plan.override} />}
        <LogLines plan={plan} />
        {targetsMet ? null : noSafePlan ? (
          <>
            <Section title={copy.NO_SAFE_PLAN_WHY}>
              <Exclusions plan={plan} />
            </Section>
            <Section title={copy.NO_SAFE_PLAN_CHECK}>
              <ul className="list-disc space-y-1 pl-5">
                {copy.NO_SAFE_PLAN_CHECKLIST.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </Section>
          </>
        ) : (
          <>
            <Section title={copy.PLAN_ITEMS_TITLE}>
              <Items items={plan.items} />
            </Section>
            <Section title={plan.already_logged ? copy.PLAN_REST_OF_DAY : copy.PLAN_COVERAGE_TITLE}>
              <Coverage plan={plan} />
            </Section>
            <Section title={copy.PLAN_EXCLUDED_TITLE}>
              <Exclusions plan={plan} />
            </Section>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-1 font-medium">{title}</h4>
      {children}
    </section>
  );
}

/** What the feeding log changed about this plan (change 2): shown on plan and targets_met. */
function LogLines({ plan }: { plan: MealPlanResult }) {
  if (plan.adjustments.length === 0 && !plan.already_logged) return null;
  return (
    <div className="space-y-1 text-muted-foreground" data-testid="log-lines">
      {plan.adjustments.map((a) => (
        <p key={`${a.nutrient}-${a.action}`} data-testid="adjustment" title={a.detail}>
          {copy.adjustedFor(a.nutrient, a.window_days)}
        </p>
      ))}
      {plan.already_logged && (
        <p data-testid="already-logged">
          {copy.alreadyLogged(
            plan.already_logged.calories,
            plan.already_logged.protein_g,
            plan.already_logged.iron_mg,
          )}
        </p>
      )}
    </div>
  );
}

export function OverrideBanner({ override }: { override: OverrideOutcome }) {
  const { nutrient, applied_value, general_value } = override;
  if (!nutrient || applied_value === null || general_value === null) return null;
  return (
    <div
      role="status"
      data-testid="override-banner"
      className="rounded-md border border-amber-400 bg-amber-50 p-3 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100"
    >
      <p className="font-medium">{copy.OVERRIDE_TITLE}</p>
      <p>{copy.overrideBody(nutrient, applied_value, general_value, UNIT_FOR_NUTRIENT[nutrient])}</p>
    </div>
  );
}

function Items({ items }: { items: PlannedItem[] }) {
  const bySlot = new Map<MealSlot, PlannedItem[]>();
  for (const item of items) bySlot.set(item.meal, [...(bySlot.get(item.meal) ?? []), item]);
  return (
    <dl className="space-y-2">
      {SLOT_ORDER.filter((slot) => bySlot.has(slot)).map((slot) => (
        <div key={slot}>
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">{copy.MEAL_SLOT_LABELS[slot]}</dt>
          {bySlot.get(slot)!.map((item) => (
            <dd key={item.food_id} className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span>{item.name}</span>
              <span className="tabular-nums text-muted-foreground" title={item.reason}>
                {copy.servingsLine(item.servings, item.serving_size, item.serving_unit)}
              </span>
            </dd>
          ))}
        </div>
      ))}
    </dl>
  );
}

/** Coverage is against what the plan set out to cover: the full day, or what remained of it
 * after today's log (full-day target minus intake, floored at 0 — mirrors the backend). */
function Coverage({ plan }: { plan: MealPlanResult }) {
  const logged = plan.already_logged;
  const remaining = (target: number, eaten: number) => (logged ? Math.max(0, target - eaten) : target);
  const rows: { key: "calories" | "protein" | "iron"; target: number }[] = [
    { key: "calories", target: remaining(plan.targets.calories.calories, logged?.calories ?? 0) },
    { key: "protein", target: remaining(plan.targets.protein.protein_g, logged?.protein_g ?? 0) },
    { key: "iron", target: remaining(plan.targets.iron.iron_mg, logged?.iron_mg ?? 0) },
  ];
  return (
    <ul className="space-y-2">
      {rows.map(({ key, target }) => {
        const percent = plan.coverage[key] * 100;
        return (
          <li key={key}>
            <div className="mb-1 flex justify-between">
              <span>{copy.COVERAGE_LABELS[key]}</span>
              <span className="tabular-nums text-muted-foreground">
                {copy.coverageLine(percent, target, UNIT_FOR_NUTRIENT[key])}
              </span>
            </div>
            <Progress value={Math.min(percent, 100)} max={100} aria-label={copy.COVERAGE_LABELS[key]}>
              <ProgressTrack>
                <ProgressIndicator />
              </ProgressTrack>
            </Progress>
          </li>
        );
      })}
    </ul>
  );
}

function Exclusions({ plan }: { plan: MealPlanResult }) {
  if (plan.exclusions.length === 0) return <p className="text-muted-foreground">{copy.PLAN_NO_EXCLUSIONS}</p>;
  return (
    <ul className="space-y-1" data-testid="exclusions">
      {plan.exclusions.map((e) => (
        <li key={e.food_id}>
          <span className="font-medium">{e.food_id.replaceAll("_", " ")}</span>
          <span className="text-muted-foreground"> — {e.reasons.join("; ")}</span>
        </li>
      ))}
    </ul>
  );
}
