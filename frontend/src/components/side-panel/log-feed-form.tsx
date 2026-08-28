"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import type { FeedingEntry, FoodSummary, LoggedFeeding } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { FEEDING_TYPE_OPTIONS, type FeedingType } from "@/lib/enums";

const DEFAULT_FOOD: Partial<Record<FeedingType, string>> = {
  breastmilk: "breast_milk",
  formula: "infant_formula_iron_fortified",
};

interface Props {
  foods: FoodSummary[] | undefined;
  foodsLoading: boolean;
  foodsError: boolean;
  /** Saves the entry to the child's log on the account and returns it priced. */
  submit: (entry: FeedingEntry) => Promise<LoggedFeeding>;
  onLogged: (logged: LoggedFeeding) => void;
}

function nowLocal(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function LogFeedForm({ foods, foodsLoading, foodsError, submit: post, onLogged }: Props) {
  const [type, setType] = useState<FeedingType>("breastmilk");
  const [foodId, setFoodId] = useState<string>(DEFAULT_FOOD.breastmilk ?? "");
  const [quantity, setQuantity] = useState("");
  const [time, setTime] = useState(nowLocal);
  const [error, setError] = useState<string | null>(null);

  const options =
    type === "water"
      ? []
      : type === "solid"
        ? (foods ?? []).filter((f) => f.category !== "milk_feed")
        : (foods ?? []).filter((f) => f.category === "milk_feed");
  const food = options.find((f) => f.id === foodId);
  const unit = food?.serving_unit === "g" ? "g" : "ml";

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

  function changeType(next: FeedingType) {
    setType(next);
    setFoodId(DEFAULT_FOOD[next] ?? "");
    setError(null);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const when = new Date(time);
    if (!time || Number.isNaN(when.getTime())) return setError(copy.LOG_ERROR_TIME);
    if (type === "solid" && !food) return setError(copy.LOG_ERROR_FOOD);
    const amount = quantity.trim() === "" ? null : Number(quantity);
    if (amount === null ? type !== "breastmilk" : !Number.isFinite(amount) || amount <= 0) {
      return setError(copy.LOG_ERROR_QUANTITY);
    }
    mutation.mutate({
      fed_at: when.toISOString(),
      feeding_type: type,
      food_id: type === "water" ? null : foodId || null,
      quantity: amount,
      unit,
    });
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={submit} aria-label={copy.LOG_ADD_TITLE}>
      <h3 className="text-sm font-medium">{copy.LOG_ADD_TITLE}</h3>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">{copy.LOG_TYPE_LABEL}</span>
        <Select value={type} onValueChange={(v) => v && changeType(v as FeedingType)}>
          <SelectTrigger id="feeding_type" className="w-full">
            <SelectValue>
              {(v: FeedingType | null) => FEEDING_TYPE_OPTIONS.find((o) => o.value === v)?.label ?? "—"}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {FEEDING_TYPE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      {type !== "water" && (
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{copy.LOG_FOOD_LABEL}</span>
          {foodsLoading ? (
            <p className="text-xs text-muted-foreground">{copy.LOG_FOODS_LOADING}</p>
          ) : foodsError ? (
            <p className="text-xs text-destructive" role="alert">
              {copy.LOG_FOODS_UNAVAILABLE}
            </p>
          ) : (
            <Select value={foodId || null} onValueChange={(v) => setFoodId((v as string | null) ?? "")}>
              <SelectTrigger id="food_id" className="w-full">
                <SelectValue>{(v: string | null) => options.find((f) => f.id === v)?.name ?? "—"}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {options.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
        {type === "breastmilk" && (
          <span className="text-xs text-muted-foreground">{copy.FORM_QUANTITY_BREASTMILK_HINT}</span>
        )}
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor="feed_time">
        <span className="font-medium">{copy.LOG_TIME_LABEL}</span>
        <Input id="feed_time" type="datetime-local" value={time} onChange={(e) => setTime(e.target.value)} />
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
