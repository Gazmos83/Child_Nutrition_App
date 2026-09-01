"use client";

import { useQuery } from "@tanstack/react-query";
import type { DailyTargetsResponse } from "@/lib/api-types";
import { fetchJson } from "@/lib/api";

export function dailyTargetsKey(childId: string | null) {
  return ["daily-targets", childId] as const;
}

/**
 * The saved child's daily reference targets, in the server's display order. Keyed on the
 * saved profile's id (design Decision 9: the panel never shows numbers for an unsaved
 * draft); invalidated by the profile-save, profile-clear, and feeding-log mutations, since
 * the tracked rows carry the logged window's flags.
 */
export function useDailyTargets(childId: string | null) {
  return useQuery<DailyTargetsResponse>({
    queryKey: dailyTargetsKey(childId),
    queryFn: () => fetchJson<DailyTargetsResponse>(`/api/children/${childId}/targets`),
    enabled: childId !== null,
  });
}
