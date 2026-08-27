"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ChildForm, ChildFormErrors } from "@/lib/child-context-store";
import { HEIGHT_REQUIRED_FROM_MONTHS, MAX_AGE_MONTHS, MAX_NOTE_CHARS } from "@/lib/child-context-store";
import * as copy from "@/lib/copy";
import {
  ACTIVITY_LEVEL_OPTIONS,
  ALLERGEN_OPTIONS,
  DIET_PREFERENCE_OPTIONS,
  SEX_OPTIONS,
  type ActivityLevel,
  type Allergen,
  type DietPreference,
  type Option,
  type Sex,
} from "@/lib/enums";

interface Props {
  form: ChildForm;
  errors: ChildFormErrors;
  isEmpty: boolean;
  hydrated: boolean;
  update: <K extends keyof ChildForm>(key: K, value: ChildForm[K]) => void;
  clear: () => void;
}

export function ChildContextForm({ form, errors, isEmpty, hydrated, update, clear }: Props) {
  const age = Number(form.age_months);
  const heightNeeded = form.age_months !== "" && Number.isInteger(age) && age >= HEIGHT_REQUIRED_FROM_MONTHS;

  return (
    <form className="flex flex-col gap-4 p-4" onSubmit={(e) => e.preventDefault()} aria-label={copy.PANEL_TITLE}>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{copy.PANEL_TITLE}</h2>
        {!isEmpty && (
          <Button type="button" variant="ghost" size="sm" onClick={clear}>
            {copy.FORM_CLEAR}
          </Button>
        )}
      </div>

      {hydrated && isEmpty && (
        <p className="rounded-md bg-muted p-3 text-sm" data-testid="panel-empty">
          {copy.PANEL_EMPTY}
        </p>
      )}

      <Field label={copy.FORM_AGE_LABEL} hint={copy.FORM_AGE_HINT} error={errors.age_months} htmlFor="age_months">
        <Input
          id="age_months"
          type="number"
          inputMode="numeric"
          min={0}
          max={MAX_AGE_MONTHS}
          step={1}
          value={form.age_months}
          onChange={(e) => update("age_months", e.target.value)}
          aria-invalid={Boolean(errors.age_months)}
        />
      </Field>

      <Field label={copy.FORM_WEIGHT_LABEL} error={errors.weight_kg} htmlFor="weight_kg">
        <Input
          id="weight_kg"
          type="number"
          inputMode="decimal"
          min={0}
          step={0.1}
          value={form.weight_kg}
          onChange={(e) => update("weight_kg", e.target.value)}
          aria-invalid={Boolean(errors.weight_kg)}
        />
      </Field>

      <Field label={copy.FORM_SEX_LABEL} error={errors.sex} htmlFor="sex">
        <EnumSelect<Sex>
          id="sex"
          value={form.sex === "" ? null : form.sex}
          options={SEX_OPTIONS}
          onChange={(v) => update("sex", v ?? "")}
        />
      </Field>

      <Field
        label={copy.FORM_HEIGHT_LABEL}
        hint={copy.FORM_HEIGHT_HINT}
        error={errors.height_cm}
        htmlFor="height_cm"
        required={heightNeeded}
      >
        <Input
          id="height_cm"
          type="number"
          inputMode="decimal"
          min={0}
          step={0.5}
          value={form.height_cm}
          onChange={(e) => update("height_cm", e.target.value)}
          aria-invalid={Boolean(errors.height_cm)}
        />
      </Field>

      <Field label={copy.FORM_DIET_LABEL} htmlFor="diet_preference">
        <EnumSelect<DietPreference>
          id="diet_preference"
          value={form.diet_preference}
          options={DIET_PREFERENCE_OPTIONS}
          onChange={(v) => v && update("diet_preference", v)}
        />
      </Field>

      <fieldset>
        <legend className="mb-1 text-sm font-medium">{copy.FORM_ALLERGIES_LABEL}</legend>
        <ul className="grid grid-cols-2 gap-1">
          {ALLERGEN_OPTIONS.map((opt) => (
            <li key={opt.value} className="flex items-center gap-2">
              <Checkbox
                id={`allergy-${opt.value}`}
                checked={form.allergies.includes(opt.value)}
                onCheckedChange={(checked) => update("allergies", toggle(form.allergies, opt.value, checked))}
              />
              <label htmlFor={`allergy-${opt.value}`} className="text-sm">
                {opt.label}
              </label>
            </li>
          ))}
        </ul>
      </fieldset>

      <Field label={copy.FORM_NOTE_LABEL} hint={copy.FORM_NOTE_HINT} error={errors.doctors_note} htmlFor="doctors_note">
        <Textarea
          id="doctors_note"
          rows={3}
          maxLength={MAX_NOTE_CHARS}
          value={form.doctors_note}
          onChange={(e) => update("doctors_note", e.target.value)}
        />
      </Field>

      <Field label={copy.FORM_ACTIVITY_LABEL} htmlFor="activity_level">
        <EnumSelect<ActivityLevel>
          id="activity_level"
          value={form.activity_level}
          options={ACTIVITY_LEVEL_OPTIONS}
          onChange={(v) => v && update("activity_level", v)}
        />
      </Field>

      {hydrated && !isEmpty && (
        <p className="text-xs text-muted-foreground">
          <Badge variant="outline">{copy.FORM_SAVED}</Badge>
        </p>
      )}
    </form>
  );
}

function toggle(list: Allergen[], value: Allergen, on: boolean): Allergen[] {
  return on ? [...new Set([...list, value])] : list.filter((v) => v !== value);
}

function Field({
  label,
  hint,
  error,
  htmlFor,
  required,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  htmlFor: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}

function EnumSelect<T extends string>({
  id,
  value,
  options,
  onChange,
}: {
  id: string;
  value: T | null;
  options: readonly Option<T>[];
  onChange: (value: T | null) => void;
}) {
  const labels = Object.fromEntries(options.map((o) => [o.value, o.label])) as Record<T, string>;
  return (
    <Select value={value} onValueChange={(v) => onChange((v as T | null) ?? null)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue>{(v: T | null) => (v ? labels[v] : "—")}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
