"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { SESSION_KEY } from "@/hooks/use-session";
import { setUnauthorizedHandler } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  useEffect(() => {
    // Any 401 from any request means the session is gone: show sign-in, keep the page.
    setUnauthorizedHandler(() => {
      client.setQueryData(SESSION_KEY, null);
      client.removeQueries({ queryKey: ["children"] });
      client.removeQueries({ queryKey: ["feedings"] });
      client.removeQueries({ queryKey: ["growth"] });
    });
    return () => setUnauthorizedHandler(null);
  }, [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
