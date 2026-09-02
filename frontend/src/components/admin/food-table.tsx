"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import type { FoodItem } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { ALLERGEN_OPTIONS, FOOD_CATEGORY_OPTIONS } from "@/lib/enums";

/** Mirrors backend/nutrition/food_admin.py:PROTECTED_FOOD_IDS; the server enforces it. */
export const PROTECTED_FOOD_IDS: readonly string[] = ["breast_milk", "infant_formula_iron_fortified"];

interface Props {
  foods: FoodItem[];
  /** The id of a food whose state is being changed right now. */
  busyId: string | null;
  onEdit: (food: FoodItem) => void;
  onToggleActive: (food: FoodItem) => void;
}

const CATEGORY_LABELS = Object.fromEntries(FOOD_CATEGORY_OPTIONS.map((o) => [o.value, o.label]));
const ALLERGEN_LABELS = Object.fromEntries(ALLERGEN_OPTIONS.map((o) => [o.value, o.label]));

function safetyFlags(food: FoodItem): string {
  const flags = [
    food.choking_hazard ? copy.ADMIN_FLAG_CHOKING : null,
    food.contains_honey ? copy.ADMIN_FLAG_HONEY : null,
    food.commonly_unpasteurized ? copy.ADMIN_FLAG_UNPASTEURIZED : null,
  ].filter((f): f is string => f !== null);
  return flags.length > 0 ? flags.join(", ") : copy.ADMIN_NONE;
}

/** Every food in the table, active first, with edit and (de)activation per row. */
export function FoodTable({ foods, busyId, onEdit, onToggleActive }: Props) {
  const [filter, setFilter] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const needle = filter.trim().toLowerCase();
  const rows = foods.filter(
    (food) =>
      (showInactive || food.is_active) &&
      (needle === "" || food.name.toLowerCase().includes(needle) || food.id.includes(needle)),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          aria-label={copy.ADMIN_FILTER_LABEL}
          placeholder={copy.ADMIN_FILTER_PLACEHOLDER}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
        <span className="flex items-center gap-2">
          <Checkbox
            id="show-inactive"
            checked={showInactive}
            onCheckedChange={(checked) => setShowInactive(Boolean(checked))}
          />
          <label htmlFor="show-inactive" className="text-sm">
            {copy.ADMIN_SHOW_INACTIVE}
          </label>
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm" data-testid="food-table">
          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_NAME}</th>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_CATEGORY}</th>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_SERVING}</th>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_AGE}</th>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_ALLERGENS}</th>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_SAFETY}</th>
              <th className="px-3 py-2 font-medium">{copy.ADMIN_COL_ACTIONS}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-muted-foreground">
                  {copy.ADMIN_NO_MATCHES}
                </td>
              </tr>
            )}
            {rows.map((food) => {
              const protectedId = PROTECTED_FOOD_IDS.includes(food.id);
              return (
                <tr
                  key={food.id}
                  className={food.is_active ? "border-t" : "border-t text-muted-foreground"}
                  data-testid="food-row"
                  data-food-id={food.id}
                >
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span>{food.name}</span>
                      {!food.is_active && <Badge variant="outline">{copy.ADMIN_INACTIVE}</Badge>}
                    </div>
                    <div className="font-mono text-xs text-muted-foreground">{food.id}</div>
                  </td>
                  <td className="px-3 py-2">{CATEGORY_LABELS[food.category] ?? food.category}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {copy.formatNumber(food.serving_size)} {food.serving_unit}
                  </td>
                  <td className="px-3 py-2">{food.min_age_months}</td>
                  <td className="px-3 py-2">
                    {food.allergens.length > 0
                      ? food.allergens.map((a) => ALLERGEN_LABELS[a] ?? a).join(", ")
                      : copy.ADMIN_NONE}
                  </td>
                  <td className="px-3 py-2">{safetyFlags(food)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <div className="flex gap-1">
                      <Button type="button" variant="outline" size="xs" onClick={() => onEdit(food)}>
                        {copy.ADMIN_EDIT}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={protectedId || busyId === food.id}
                        title={protectedId ? copy.ADMIN_PROTECTED : undefined}
                        onClick={() => onToggleActive(food)}
                      >
                        {food.is_active ? copy.ADMIN_DEACTIVATE : copy.ADMIN_ACTIVATE}
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">{copy.ADMIN_DEACTIVATE_NOTE}</p>
    </div>
  );
}
