"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import type { GrowthMeasurement, GrowthMeasurementWrite } from "@/lib/api-types";
import { MAX_HEIGHT_CM, MAX_WEIGHT_KG, parseIsoDate, todayIsoDate } from "@/lib/child-context-store";
import * as copy from "@/lib/copy";

interface Props {
  /** The saved profile's date of birth (YYYY-MM-DD); the earliest day a measurement can have. */
  birthDate: string | null;
  /** Saves the measurement to the child's growth log on the account. */
  submit: (body: GrowthMeasurementWrite) => Promise<GrowthMeasurement>;
  onLogged: (measurement: GrowthMeasurement) => void;
}

export function LogMeasurementForm({ birthDate, submit: post, onLogged }: Props) {
  const today = todayIsoDate();
  const [measuredOn, setMeasuredOn] = useState(today);
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: post,
    onSuccess: (measurement) => {
      onLogged(measurement);
      setWeight("");
      setHeight("");
      setError(null);
    },
    // A 422 or 409 carries the server's own parent-facing reason (before the birth date, a
    // day already recorded); anything else gets the generic line.
    onError: (e: unknown) =>
      setError(
        e instanceof ApiError && (e.status === 422 || e.status === 409)
          ? e.detail
          : copy.GROWTH_ADD_FAILED,
      ),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    // ISO dates compare correctly as strings.
    const dateOk =
      parseIsoDate(measuredOn) !== null &&
      measuredOn <= today &&
      (birthDate === null || measuredOn >= birthDate);
    if (!dateOk) return setError(copy.GROWTH_ERROR_DATE);
    const weightKg = Number(weight);
    if (weight.trim() === "" || !Number.isFinite(weightKg) || weightKg <= 0 || weightKg > MAX_WEIGHT_KG) {
      return setError(copy.FORM_ERROR_WEIGHT);
    }
    let heightCm: number | null = null;
    if (height.trim() !== "") {
      heightCm = Number(height);
      if (!Number.isFinite(heightCm) || heightCm <= 0 || heightCm > MAX_HEIGHT_CM) {
        return setError(copy.FORM_ERROR_HEIGHT);
      }
    }
    mutation.mutate({ measured_on: measuredOn, weight_kg: weightKg, height_cm: heightCm });
  }

  return (
    // noValidate: the date input's min/max guide the picker, but the messages a parent
    // reads come from copy.ts, not the browser's own tooltip.
    <form className="flex flex-col gap-3" onSubmit={submit} aria-label={copy.GROWTH_ADD_TITLE} noValidate>
      <h3 className="text-sm font-medium">{copy.GROWTH_ADD_TITLE}</h3>

      <label className="flex flex-col gap-1 text-sm" htmlFor="measured_on">
        <span className="font-medium">{copy.GROWTH_DATE_LABEL}</span>
        <Input
          id="measured_on"
          type="date"
          min={birthDate ?? undefined}
          max={today}
          value={measuredOn}
          onChange={(e) => setMeasuredOn(e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor="growth_weight">
        <span className="font-medium">{copy.FORM_WEIGHT_LABEL}</span>
        <Input
          id="growth_weight"
          type="number"
          inputMode="decimal"
          min={0}
          step={0.1}
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor="growth_height">
        <span className="font-medium">{copy.FORM_HEIGHT_LABEL}</span>
        <Input
          id="growth_height"
          type="number"
          inputMode="decimal"
          min={0}
          step={0.5}
          value={height}
          onChange={(e) => setHeight(e.target.value)}
        />
        <span className="text-xs text-muted-foreground">{copy.GROWTH_HEIGHT_HINT}</span>
      </label>

      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" size="sm" disabled={mutation.isPending}>
        {mutation.isPending ? copy.GROWTH_ADDING : copy.GROWTH_ADD}
      </Button>
    </form>
  );
}
