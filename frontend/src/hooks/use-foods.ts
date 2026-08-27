"use client";

import { useQuery } from "@tanstack/react-query";
import type { FoodSummary } from "@/lib/api-types";

/** The food table for the picker: fetched once per session, the table changes by release. */
export function useFoods() {
  return useQuery<FoodSummary[]>({
    queryKey: ["foods"],
    queryFn: async () => {
      const res = await fetch("/api/foods");
      if (!res.ok) throw new Error(res.statusText);
      return (await res.json()) as FoodSummary[];
    },
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });
}
