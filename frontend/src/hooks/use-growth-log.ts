"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { GrowthCurvesResponse, GrowthMeasurement, GrowthMeasurementWrite } from "@/lib/api-types";
import { CHILDREN_KEY } from "@/hooks/use-child-context";
import { dailyTargetsKey } from "@/hooks/use-daily-targets";
import { fetchJson } from "@/lib/api";
import { addMeasurement, removeMeasurement, sortNewest } from "@/lib/growth-log-store";

export function growthKey(childId: string | null) {
  return ["growth", childId] as const;
}

/** The child's growth measurements from the account, newest first, each with its WHO assessment. */
export function useGrowthLog(childId: string | null) {
  const queryClient = useQueryClient();
  const key = growthKey(childId);
  const query = useQuery<GrowthMeasurement[]>({
    queryKey: key,
    queryFn: () => fetchJson<GrowthMeasurement[]>(`/api/children/${childId}/growth`),
    enabled: childId !== null,
  });
  const measurements = useMemo(() => sortNewest(query.data ?? []), [query.data]);

  // The newest measurement writes through to the profile's weight and height, which the
  // Child tab shows and the daily targets are computed from.
  const refreshProfileReaders = () => {
    queryClient.invalidateQueries({ queryKey: CHILDREN_KEY });
    queryClient.invalidateQueries({ queryKey: dailyTargetsKey(childId) });
  };

  const add = useMutation({
    mutationFn: (body: GrowthMeasurementWrite) =>
      fetchJson<GrowthMeasurement>(`/api/children/${childId}/growth`, { method: "POST", body }),
    onSuccess: (measurement) => {
      queryClient.setQueryData<GrowthMeasurement[]>(key, (current) =>
        addMeasurement(current ?? [], measurement),
      );
      refreshProfileReaders();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      fetchJson<void>(`/api/children/${childId}/growth/${id}`, { method: "DELETE" }),
    onSuccess: (_, id) => {
      queryClient.setQueryData<GrowthMeasurement[]>(key, (current) =>
        removeMeasurement(current ?? [], id),
      );
      refreshProfileReaders();
    },
  });

  return {
    childId,
    measurements,
    hydrated: childId === null || !query.isPending,
    unavailable: query.isError,
    add: add.mutateAsync,
    remove: remove.mutate,
    removeFailed: remove.isError,
  };
}

export type GrowthLogState = ReturnType<typeof useGrowthLog>;

export function growthCurvesKey(childId: string | null) {
  return ["growth-curves", childId] as const;
}

/**
 * The WHO percentile curves for the child's sex and table. They change only when the
 * profile changes (sex, or crossing 24 months), so the profile save invalidates them.
 */
export function useGrowthCurves(childId: string | null) {
  return useQuery<GrowthCurvesResponse>({
    queryKey: growthCurvesKey(childId),
    queryFn: () => fetchJson<GrowthCurvesResponse>(`/api/children/${childId}/growth/curves`),
    enabled: childId !== null,
    staleTime: Number.POSITIVE_INFINITY,
  });
}
