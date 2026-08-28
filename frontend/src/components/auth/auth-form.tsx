"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { useSession } from "@/hooks/use-session";
import { ApiError } from "@/lib/api";
import * as copy from "@/lib/copy";

type Session = ReturnType<typeof useSession>;
type Mode = "sign-in" | "create";

const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 128;

export function AuthForm({ session }: { session: Session }) {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const mutation = mode === "sign-in" ? session.signIn : session.register;
  const error = errorMessage(mutation.error);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (mutation.isPending) return;
    mutation.mutate({ email: email.trim(), password });
  }

  function switchMode() {
    session.signIn.reset();
    session.register.reset();
    setMode(mode === "sign-in" ? "create" : "sign-in");
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{copy.AUTH_TITLE}</CardTitle>
          <CardDescription>{copy.AUTH_INTRO}</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submit} aria-label={copy.AUTH_TITLE}>
            <label className="flex flex-col gap-1 text-sm" htmlFor="email">
              <span className="font-medium">{copy.AUTH_EMAIL}</span>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm" htmlFor="password">
              <span className="font-medium">{copy.AUTH_PASSWORD}</span>
              <Input
                id="password"
                type="password"
                autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
                required
                minLength={MIN_PASSWORD_LENGTH}
                maxLength={MAX_PASSWORD_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {mode === "create" && (
                <span className="text-xs text-muted-foreground">{copy.AUTH_PASSWORD_HINT}</span>
              )}
            </label>
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending
                ? copy.AUTH_WORKING
                : mode === "sign-in"
                  ? copy.AUTH_SIGN_IN
                  : copy.AUTH_CREATE}
            </Button>
            <Button type="button" variant="link" size="sm" onClick={switchMode}>
              {mode === "sign-in" ? copy.AUTH_SWITCH_TO_CREATE : copy.AUTH_SWITCH_TO_SIGN_IN}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

/** The server's own message for a refused sign-in or a taken email; ours for anything else. */
function errorMessage(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError && (error.status === 401 || error.status === 409)) {
    return error.detail;
  }
  return copy.AUTH_FAILED;
}
