"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  FoodImportRequest,
  FoodImportResult,
  FoodTableAdminResponse,
  FoodWrite,
  FoodWriteResponse,
} from "@/lib/api-types";
import { fetchJson } from "@/lib/api";

export const ADMIN_FOODS_KEY = ["admin", "foods"] as const;
const BASE = "/api/admin/foods";

/** The whole food table for administrators, and the writes that move it to a new revision. */
export function useAdminFoods(enabled: boolean) {
  const queryClient = useQueryClient();
  const query = useQuery<FoodTableAdminResponse>({
    queryKey: ADMIN_FOODS_KEY,
    queryFn: () => fetchJson<FoodTableAdminResponse>(BASE),
    enabled,
  });
  // Every write is a new revision: refetch the admin table and the picker the parent uses.
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ADMIN_FOODS_KEY });
    queryClient.invalidateQueries({ queryKey: ["foods"] });
  };
  const create = useMutation({
    mutationFn: (body: FoodWrite) => fetchJson<FoodWriteResponse>(BASE, { method: "POST", body }),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: (body: FoodWrite) =>
      fetchJson<FoodWriteResponse>(`${BASE}/${body.id}`, { method: "PUT", body }),
    onSuccess: refresh,
  });
  const setActive = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      fetchJson<FoodWriteResponse>(`${BASE}/${id}/${active ? "activate" : "deactivate"}`, {
        method: "POST",
      }),
    onSuccess: refresh,
  });
  const importFile = useMutation({
    mutationFn: (body: FoodImportRequest) =>
      fetchJson<FoodImportResult>(`${BASE}/import`, { method: "POST", body }),
    onSuccess: (result) => {
      if (result.applied) refresh();
    },
  });
  return {
    table: query.data ?? null,
    hydrated: !query.isPending,
    unavailable: query.isError,
    create: create.mutateAsync,
    update: update.mutateAsync,
    setActive: setActive.mutateAsync,
    setActiveFailed: setActive.isError,
    importFile: importFile.mutateAsync,
  };
}

export type AdminFoodsState = ReturnType<typeof useAdminFoods>;
