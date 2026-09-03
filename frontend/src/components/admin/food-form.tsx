"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { EnumSelect } from "@/components/side-panel/child-context-form";
import {
  emptyFoodForm,
  fromFood,
  SAFETY_FIELDS,
  toFoodWrite,
  type FoodForm,
  type FoodFormErrors,
  type YesNo,
} from "@/lib/admin-food-form";
import type { FoodItem, FoodWrite } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { ALLERGEN_OPTIONS, FOOD_CATEGORY_OPTIONS, type Allergen, type FoodCategory } from "@/lib/enums";

interface Props {
  /** The food being edited, or null for a new one. */
  initial: FoodItem | null;
  /**
   * A prefilled starting point for a new food (e.g. a live external lookup, hard rule 10),
   * used instead of an empty form when `initial` is null. Never used to prefill the safety
   * questions — those stay unanswered like any new food (design Decision 8).
   */
  initialForm?: FoodForm;
  busy: boolean;
  /** The server's refusal, shown verbatim (a 409 duplicate id, a 422 rule). */
  serverError: string | null;
  onSubmit: (value: FoodWrite) => void;
  onCancel: () => void;
}

const SAFETY_LABELS: Record<(typeof SAFETY_FIELDS)[number], string> = {
  choking_hazard: copy.ADMIN_SAFETY_CHOKING,
  contains_honey: copy.ADMIN_SAFETY_HONEY,
  commonly_unpasteurized: copy.ADMIN_SAFETY_UNPASTEURIZED,
};

const NUMBER_FIELDS: readonly [keyof FoodForm, string][] = [
  ["calories", copy.ADMIN_FIELD_CALORIES],
  ["protein_g", copy.ADMIN_FIELD_PROTEIN],
  ["fat_g", copy.ADMIN_FIELD_FAT],
  ["carbohydrate_g", copy.ADMIN_FIELD_CARBS],
  ["iron_mg", copy.ADMIN_FIELD_IRON],
  ["calcium_mg", copy.ADMIN_FIELD_CALCIUM],
];

// A separate, visibly optional group: an empty box must read as "leave it blank", never as
// a value to guess (design Decision 6; hard rule 5).
const MICRONUTRIENT_LABELS: readonly [keyof FoodForm, string][] = [
  ["zinc_mg", copy.ADMIN_FIELD_ZINC],
  ["vitamin_a_ug", copy.ADMIN_FIELD_VITAMIN_A],
  ["iodine_ug", copy.ADMIN_FIELD_IODINE],
  ["vitamin_b12_ug", copy.ADMIN_FIELD_VITAMIN_B12],
  ["folate_ug", copy.ADMIN_FIELD_FOLATE],
  ["vitamin_c_mg", copy.ADMIN_FIELD_VITAMIN_C],
  ["fiber_g", copy.ADMIN_FIELD_FIBER],
];

function toggle(list: Allergen[], value: Allergen, on: boolean): Allergen[] {
  return on ? [...new Set([...list, value])] : list.filter((v) => v !== value);
}

/** Create or edit one food. Nothing about safety is preselected (design Decision 8). */
export function FoodForm({ initial, initialForm, busy, serverError, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<FoodForm>(
    () => initialForm ?? (initial ? fromFood(initial) : emptyFoodForm()),
  );
  const [errors, setErrors] = useState<FoodFormErrors>({});
  const update = <K extends keyof FoodForm>(key: K, value: FoodForm[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => (e[key] ? { ...e, [key]: undefined } : e));
  };
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const result = toFoodWrite(form);
    if (!result.ok) {
      setErrors(result.errors);
      return;
    }
    // Editing keeps the food's state; activation has its own buttons.
    onSubmit(initial ? { ...result.value, is_active: initial.is_active } : result.value);
  };

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4" data-testid="food-form">
      <h3 className="text-base font-medium">
        {initial ? copy.ADMIN_FORM_EDIT_TITLE : copy.ADMIN_FORM_NEW_TITLE}
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="food-id" label={copy.ADMIN_FIELD_ID} hint={copy.ADMIN_FIELD_ID_HINT} error={errors.id}>
          <Input
            id="food-id"
            value={form.id}
            disabled={initial !== null}
            onChange={(e) => update("id", e.target.value)}
            aria-invalid={Boolean(errors.id)}
          />
        </Field>
        <Field id="food-name" label={copy.ADMIN_FIELD_NAME} error={errors.name}>
          <Input
            id="food-name"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            aria-invalid={Boolean(errors.name)}
          />
        </Field>
        <Field id="food-category" label={copy.ADMIN_FIELD_CATEGORY} error={errors.category}>
          <EnumSelect<FoodCategory>
            id="food-category"
            value={form.category === "" ? null : form.category}
            options={FOOD_CATEGORY_OPTIONS}
            onChange={(value) => update("category", value ?? "")}
          />
        </Field>
        <Field
          id="food-min-age"
          label={copy.ADMIN_FIELD_MIN_AGE}
          hint={copy.ADMIN_FIELD_MIN_AGE_HINT}
          error={errors.min_age_months}
        >
          <Input
            id="food-min-age"
            type="number"
            inputMode="numeric"
            value={form.min_age_months}
            onChange={(e) => update("min_age_months", e.target.value)}
            aria-invalid={Boolean(errors.min_age_months)}
          />
        </Field>
        <Field
          id="food-serving-size"
          label={copy.ADMIN_FIELD_SERVING_SIZE}
          hint={copy.ADMIN_FIELD_SERVING_HINT}
          error={errors.serving_size}
        >
          <Input
            id="food-serving-size"
            type="number"
            step="any"
            inputMode="decimal"
            value={form.serving_size}
            onChange={(e) => update("serving_size", e.target.value)}
            aria-invalid={Boolean(errors.serving_size)}
          />
        </Field>
        <Field id="food-serving-unit" label={copy.ADMIN_FIELD_SERVING_UNIT} error={errors.serving_unit}>
          <Input
            id="food-serving-unit"
            value={form.serving_unit}
            onChange={(e) => update("serving_unit", e.target.value)}
            aria-invalid={Boolean(errors.serving_unit)}
          />
        </Field>
        {NUMBER_FIELDS.map(([key, label]) => (
          <Field key={key} id={`food-${key}`} label={label} error={errors[key]}>
            <Input
              id={`food-${key}`}
              type="number"
              step="any"
              inputMode="decimal"
              value={form[key] as string}
              onChange={(e) => update(key, e.target.value as FoodForm[typeof key])}
              aria-invalid={Boolean(errors[key])}
            />
          </Field>
        ))}
      </div>

      <fieldset>
        <legend className="mb-1 text-sm font-medium">{copy.ADMIN_MICRONUTRIENTS_LEGEND}</legend>
        <p className="mb-2 text-xs text-muted-foreground">{copy.ADMIN_MICRONUTRIENTS_HINT}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {MICRONUTRIENT_LABELS.map(([key, label]) => (
            <Field key={key} id={`food-${key}`} label={label} error={errors[key]}>
              <Input
                id={`food-${key}`}
                type="number"
                step="any"
                inputMode="decimal"
                value={form[key] as string}
                onChange={(e) => update(key, e.target.value as FoodForm[typeof key])}
                aria-invalid={Boolean(errors[key])}
              />
            </Field>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-1 text-sm font-medium">{copy.ADMIN_FIELD_ALLERGENS}</legend>
        <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3">
          {ALLERGEN_OPTIONS.map((opt) => (
            <li key={opt.value} className="flex items-center gap-2">
              <Checkbox
                id={`food-allergen-${opt.value}`}
                checked={form.allergens.includes(opt.value)}
                onCheckedChange={(checked) => update("allergens", toggle(form.allergens, opt.value, checked))}
              />
              <label htmlFor={`food-allergen-${opt.value}`} className="text-sm">
                {opt.label}
              </label>
            </li>
          ))}
        </ul>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{copy.ADMIN_SAFETY_LEGEND}</legend>
        {SAFETY_FIELDS.map((field) => (
          <div key={field} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span id={`food-${field}-label`} className="text-sm">
                {SAFETY_LABELS[field]}
              </span>
              <div role="radiogroup" aria-labelledby={`food-${field}-label`} className="flex gap-1">
                {(["yes", "no"] as const).map((answer: YesNo) => (
                  <Button
                    key={answer}
                    type="button"
                    role="radio"
                    aria-checked={form[field] === answer}
                    variant={form[field] === answer ? "default" : "outline"}
                    size="sm"
                    onClick={() => update(field, answer)}
                  >
                    {answer === "yes" ? copy.ADMIN_YES : copy.ADMIN_NO}
                  </Button>
                ))}
              </div>
            </div>
            {errors[field] && (
              <p className="text-xs text-destructive" role="alert">
                {errors[field]}
              </p>
            )}
          </div>
        ))}
      </fieldset>

      <Field id="food-source" label={copy.ADMIN_FIELD_SOURCE} hint={copy.ADMIN_FIELD_SOURCE_HINT} error={errors.source}>
        <Input
          id="food-source"
          value={form.source}
          onChange={(e) => update("source", e.target.value)}
          aria-invalid={Boolean(errors.source)}
        />
      </Field>
      <Field id="food-notes" label={copy.ADMIN_FIELD_NOTES}>
        <Textarea id="food-notes" rows={2} value={form.notes} onChange={(e) => update("notes", e.target.value)} />
      </Field>

      {serverError && (
        <p className="text-sm text-destructive" role="alert" data-testid="food-form-server-error">
          {serverError}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? copy.ADMIN_SAVING : copy.ADMIN_SAVE}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {copy.ADMIN_CANCEL}
        </Button>
      </div>
    </form>
  );
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
