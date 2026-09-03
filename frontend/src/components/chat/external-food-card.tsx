"use client";

import { useState } from "react";
import { FoodForm } from "@/components/admin/food-form";
import { Button } from "@/components/ui/button";
import { useAdminFoods } from "@/hooks/use-admin-foods";
import { ApiError } from "@/lib/api";
import { fromExternalCitation } from "@/lib/admin-food-form";
import type { ExternalFoodCitation } from "@/lib/api-types";
import * as copy from "@/lib/copy";

const NUTRIENT_LABELS: readonly [keyof ExternalFoodCitation["nutrients"], string, string][] = [
  ["calories", copy.ADMIN_FIELD_CALORIES, "kcal"],
  ["protein_g", copy.ADMIN_FIELD_PROTEIN, "g"],
  ["fat_g", copy.ADMIN_FIELD_FAT, "g"],
  ["carbohydrate_g", copy.ADMIN_FIELD_CARBS, "g"],
  ["iron_mg", copy.ADMIN_FIELD_IRON, "mg"],
  ["calcium_mg", copy.ADMIN_FIELD_CALCIUM, "mg"],
];

function detailOf(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.detail || fallback;
  return fallback;
}

/**
 * A live, whitelisted third-party nutrient match for a food the internal table missed
 * (hard rule 10). Deliberately styled apart from `Citations` — this is never a pediatric
 * guideline. `admin_approval_eligible` alone decides whether the approval action renders;
 * the write it leads to is independently gated server-side by `AdminUser`.
 */
export function ExternalFoodCard({
  citation,
  isAdmin,
}: {
  citation: ExternalFoodCitation;
  isAdmin: boolean;
}) {
  const [approving, setApproving] = useState(false);
  const [added, setAdded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const admin = useAdminFoods(false);

  const canApprove = citation.admin_approval_eligible && isAdmin && !added;

  return (
    <section className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
      <h4 className="font-medium">{copy.EXTERNAL_FOOD_TITLE}</h4>
      <p className="mt-1">
        <span className="font-medium">{citation.matched_name}</span> —{" "}
        <a href={citation.source_url} target="_blank" rel="noreferrer" className="underline">
          {citation.source_label}
        </a>{" "}
        <span className="text-muted-foreground">
          ({copy.externalFoodRetrieved(citation.retrieved_at)})
        </span>
      </p>
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">
        {NUTRIENT_LABELS.map(([key, label, unit]) => {
          const value = citation.nutrients[key];
          return (
            <li key={key} className="text-muted-foreground">
              {label}: {value === null ? "—" : `${value} ${unit}`}
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-muted-foreground">{citation.disclaimer}</p>
      {added && <p className="mt-2 font-medium">{copy.EXTERNAL_FOOD_ADDED}</p>}
      {canApprove && !approving && (
        <Button className="mt-2" size="sm" variant="outline" onClick={() => setApproving(true)}>
          {copy.EXTERNAL_FOOD_ADD}
        </Button>
      )}
      {canApprove && approving && (
        <div className="mt-3 border-t pt-3">
          <FoodForm
            initial={null}
            initialForm={fromExternalCitation(citation)}
            busy={busy}
            serverError={serverError}
            onSubmit={(value) => {
              setBusy(true);
              setServerError(null);
              admin.create(value).then(
                () => {
                  setBusy(false);
                  setApproving(false);
                  setAdded(true);
                },
                (e: unknown) => {
                  setBusy(false);
                  setServerError(detailOf(e, copy.EXTERNAL_FOOD_ADD_FAILED));
                },
              );
            }}
            onCancel={() => {
              setApproving(false);
              setServerError(null);
            }}
          />
        </div>
      )}
    </section>
  );
}
