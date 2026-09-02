"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Credentials, CurrentUser } from "@/lib/api-types";
import { ApiError, fetchJson } from "@/lib/api";

export const SESSION_KEY = ["session"] as const;

async function whoAmI(): Promise<CurrentUser | null> {
  try {
    return await fetchJson<CurrentUser>("/api/auth/me");
  } catch (error) {
    // Signed out is a normal state, not a query error.
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** The signed-in account, or null; plus sign-in, create-account, and sign-out. */
export function useSession() {
  const queryClient = useQueryClient();
  const query = useQuery<CurrentUser | null>({
    queryKey: SESSION_KEY,
    queryFn: whoAmI,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

  const signedIn = (user: CurrentUser) => {
    // A different account may be signing in on the same page: nothing cached may carry over.
    queryClient.removeQueries({ queryKey: ["children"] });
    queryClient.removeQueries({ queryKey: ["feedings"] });
    queryClient.removeQueries({ queryKey: ["growth"] });
    queryClient.removeQueries({ queryKey: ["growth-curves"] });
    queryClient.setQueryData(SESSION_KEY, user);
  };

  const signIn = useMutation({
    mutationFn: (credentials: Credentials) =>
      fetchJson<CurrentUser>("/api/auth/login", { method: "POST", body: credentials }),
    onSuccess: signedIn,
  });
  const register = useMutation({
    mutationFn: (credentials: Credentials) =>
      fetchJson<CurrentUser>("/api/auth/register", { method: "POST", body: credentials }),
    onSuccess: signedIn,
  });
  const signOut = useMutation({
    mutationFn: () => fetchJson<void>("/api/auth/logout", { method: "POST" }),
    onSettled: () => {
      // Whatever the server said, this browser is signed out: drop every account-scoped cache.
      queryClient.setQueryData(SESSION_KEY, null);
      queryClient.removeQueries({ queryKey: ["children"] });
      queryClient.removeQueries({ queryKey: ["feedings"] });
      queryClient.removeQueries({ queryKey: ["growth"] });
      queryClient.removeQueries({ queryKey: ["growth-curves"] });
    },
  });

  return {
    user: query.data ?? null,
    isPending: query.isPending,
    isError: query.isError,
    signIn,
    register,
    signOut,
  };
}
