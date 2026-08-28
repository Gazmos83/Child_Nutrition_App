"use client";

import { AuthForm } from "@/components/auth/auth-form";
import { useSession } from "@/hooks/use-session";
import { SESSION_LOADING } from "@/lib/copy";
import { ChatPage } from "./chat-page";

/** Sign-in first: the chat, the child's details, and the log all belong to an account. */
export function AppGate() {
  const session = useSession();
  if (session.isPending) {
    return (
      <main className="flex min-h-dvh items-center justify-center p-4">
        <p className="text-sm text-muted-foreground" role="status">
          {SESSION_LOADING}
        </p>
      </main>
    );
  }
  if (!session.user) return <AuthForm session={session} />;
  return <ChatPage user={session.user} onSignOut={() => session.signOut.mutate()} />;
}
