"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import type { ChildProfile } from "@/lib/api-types";
import { ApiError, fetchJson } from "@/lib/api";
import {
  EMPTY_CHILD_FORM,
  fromProfile,
  toChildContext,
  type ChildForm,
} from "@/lib/child-context-store";

export const CHILDREN_KEY = ["children"] as const;

/**
 * The child's details, saved to the account. The UI keeps one child per account today:
 * the form edits a local draft and saves it as the account's first profile (create or
 * replace); the chat sends that profile's id.
 */
export function useChildContext() {
  const queryClient = useQueryClient();
  const children = useQuery<ChildProfile[]>({
    queryKey: CHILDREN_KEY,
    queryFn: () => fetchJson<ChildProfile[]>("/api/children"),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const profile = children.data?.[0] ?? null;

  // null means "nothing edited since the last save": the form shows the stored profile.
  const [draft, setDraft] = useState<ChildForm | null>(null);
  const form = useMemo(
    () => draft ?? (profile ? fromProfile(profile) : EMPTY_CHILD_FORM),
    [draft, profile],
  );
  const result = useMemo(() => toChildContext(form), [form]);

  const update = useCallback(
    <K extends keyof ChildForm>(key: K, value: ChildForm[K]) => {
      // Not before the saved profile has loaded: a draft typed over an empty form would
      // silently mask the stored values once they arrive.
      if (children.isPending) return;
      setDraft({ ...form, [key]: value });
    },
    [form, children.isPending],
  );

  const save = useMutation({
    mutationFn: async () => {
      if (!result.child) throw new Error("form is not valid");
      return profile
        ? fetchJson<ChildProfile>(`/api/children/${profile.id}`, {
            method: "PUT",
            body: result.child,
          })
        : fetchJson<ChildProfile>("/api/children", { method: "POST", body: result.child });
    },
    onSuccess: (saved) => {
      queryClient.setQueryData<ChildProfile[]>(CHILDREN_KEY, [saved]);
      // The saved profile is what the daily-targets panel reads (design Decision 9), and
      // the growth curves follow its sex and 24-month table.
      queryClient.invalidateQueries({ queryKey: ["daily-targets"] });
      queryClient.invalidateQueries({ queryKey: ["growth-curves"] });
      setDraft(null);
    },
  });

  const clear = useMutation({
    mutationFn: async () => {
      if (profile) await fetchJson<void>(`/api/children/${profile.id}`, { method: "DELETE" });
    },
    onSuccess: () => {
      queryClient.setQueryData<ChildProfile[]>(CHILDREN_KEY, []);
      queryClient.removeQueries({ queryKey: ["feedings"] });
      queryClient.removeQueries({ queryKey: ["growth"] });
      queryClient.removeQueries({ queryKey: ["growth-curves"] });
      queryClient.removeQueries({ queryKey: ["daily-targets"] });
      setDraft(null);
    },
  });

  return {
    form,
    update,
    save: () => save.mutate(),
    saving: save.isPending,
    saveFailed: save.isError,
    // A 422 carries the server's own reason (a birth date the server reads a month apart
    // from this browser near a birthday, say); anything else gets the generic line.
    saveError:
      save.error instanceof ApiError && save.error.status === 422 ? save.error.detail : null,
    clear: () => clear.mutate(),
    clearFailed: clear.isError,
    dirty: draft !== null,
    hydrated: !children.isPending,
    profile,
    childId: profile?.id ?? null,
    ...result,
  };
}

export type ChildContextState = ReturnType<typeof useChildContext>;
