"use client";

import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import type { FeedingEntry, FeedingUnit, FoodSummary, LoggedFeeding } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { FEEDING_TYPE_OPTIONS, type FeedingType } from "@/lib/enums";

const BREASTFED_FOOD = "breast_milk";

type MealSlot = (typeof copy.LOG_WHEN_OPTIONS)[number]["value"];

// Representative local times per slot; time-of-day never feeds a tool (they all reduce
// to the local calendar day), so this only keeps the log reading in meal order.
const SLOT_TIMES: Record<Exclude<MealSlot, "breastfed">, [number, number]> = {
  breakfast: [8, 0],
  lunch: [12, 30],
  snack: [15, 30],
  dinner: [18, 0],
};

function fedAt(slot: MealSlot): string {
  if (slot === "breastfed") return new Date().toISOString();
  const d = new Date();
  d.setHours(...SLOT_TIMES[slot], 0, 0);
  return d.toISOString();
}

/** One searchable choice; `kind` carries the feeding type the pick implies. */
interface FoodChoice {
  id: string | null;
  name: string;
  kind: FeedingType;
  unit: FeedingUnit;
}

function toChoice(food: FoodSummary): FoodChoice {
  return {
    id: food.id,
    name: food.name,
    kind:
      food.category === "milk_feed"
        ? food.id === BREASTFED_FOOD
          ? "breastmilk"
          : "formula"
        : "solid",
    unit: food.serving_unit === "g" ? "g" : "ml",
  };
}

const WATER_CHOICE: FoodChoice = {
  id: null,
  name: FEEDING_TYPE_OPTIONS.find((o) => o.value === "water")?.label ?? "Water",
  kind: "water",
  unit: "ml",
};

interface Props {
  foods: FoodSummary[] | undefined;
  foodsLoading: boolean;
  foodsError: boolean;
  /** Saves the entry to the child's log on the account and returns it priced. */
  submit: (entry: FeedingEntry) => Promise<LoggedFeeding>;
  onLogged: (logged: LoggedFeeding) => void;
}

export function LogFeedForm({ foods, foodsLoading, foodsError, submit: post, onLogged }: Props) {
  const [slot, setSlot] = useState<MealSlot>("breastfed");
  const [selection, setSelection] = useState<FoodChoice | null>(null);
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState<string | null>(null);

  const choices = useMemo(
    () => [WATER_CHOICE, ...(foods ?? []).map(toChoice)],
    [foods],
  );

  const breastfed = slot === "breastfed";
  const derivedType: FeedingType = breastfed ? "breastmilk" : selection?.kind ?? "solid";
  const unit: FeedingUnit = breastfed || !selection ? "ml" : selection.unit;

  const mutation = useMutation({
    mutationFn: post,
    onSuccess: (logged) => {
      onLogged(logged);
      setQuantity("");
      setError(null);
    },
    // A 422 carries the server's own parent-facing reason (unknown food, wrong unit).
    onError: (e: unknown) =>
      setError(e instanceof ApiError && e.status === 422 ? e.detail : copy.LOG_ADD_FAILED),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!breastfed && !selection) return setError(copy.LOG_ERROR_FOOD);
    const amount = quantity.trim() === "" ? null : Number(quantity);
    if (amount === null ? derivedType !== "breastmilk" : !Number.isFinite(amount) || amount <= 0) {
      return setError(copy.LOG_ERROR_QUANTITY);
    }
    mutation.mutate({
      fed_at: fedAt(slot),
      feeding_type: derivedType,
      food_id: breastfed ? BREASTFED_FOOD : selection?.id ?? null,
      quantity: amount,
      unit: derivedType === "solid" ? unit : "ml",
    });
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={submit} aria-label={copy.LOG_ADD_TITLE}>
      <h3 className="text-sm font-medium">{copy.LOG_ADD_TITLE}</h3>

      <fieldset className="flex flex-col gap-1 text-sm">
        <legend className="mb-1 font-medium">{copy.LOG_TIME_LABEL}</legend>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={copy.LOG_TIME_LABEL}>
          {copy.LOG_WHEN_OPTIONS.map((o) => (
            <Button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={slot === o.value}
              variant={slot === o.value ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setSlot(o.value);
                setError(null);
              }}
            >
              {o.label}
            </Button>
          ))}
        </div>
      </fieldset>

      {!breastfed && (
        <label className="flex flex-col gap-1 text-sm" htmlFor="food_search">
          <span className="font-medium">{copy.LOG_FOOD_LABEL}</span>
          {foodsLoading ? (
            <p className="text-xs text-muted-foreground">{copy.LOG_FOODS_LOADING}</p>
          ) : foodsError ? (
            <p className="text-xs text-destructive" role="alert">
              {copy.LOG_FOODS_UNAVAILABLE}
            </p>
          ) : (
            <Combobox
              items={choices}
              value={selection}
              onValueChange={(choice) => {
                setSelection(choice);
                setError(null);
              }}
              itemToStringLabel={(choice: FoodChoice) => choice.name}
              filter={(choice: FoodChoice, query: string) =>
                choice.name.toLowerCase().includes(query.trim().toLowerCase())
              }
              limit={7}
            >
              <ComboboxInput id="food_search" placeholder={copy.LOG_FOOD_SEARCH_PLACEHOLDER} />
              <ComboboxContent>
                <ComboboxEmpty>{copy.LOG_FOOD_NO_MATCH}</ComboboxEmpty>
                <ComboboxList>
                  {(choice: FoodChoice) => (
                    <ComboboxItem key={choice.id ?? "water"} value={choice}>
                      {choice.name}
                    </ComboboxItem>
                  )}
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
          )}
        </label>
      )}

      <label className="flex flex-col gap-1 text-sm" htmlFor="feed_quantity">
        <span className="font-medium">
          {copy.LOG_QUANTITY_LABEL} ({unit})
        </span>
        <Input
          id="feed_quantity"
          type="number"
          inputMode="decimal"
          min={0}
          step={unit === "g" ? 1 : 10}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
        {derivedType === "breastmilk" && (
          <span className="text-xs text-muted-foreground">{copy.FORM_QUANTITY_BREASTMILK_HINT}</span>
        )}
      </label>

      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" size="sm" disabled={mutation.isPending}>
        {mutation.isPending ? copy.LOG_ADDING : copy.LOG_ADD}
      </Button>
    </form>
  );
}
