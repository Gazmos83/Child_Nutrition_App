"use client";

import Link from "next/link";
import { AuthForm } from "@/components/auth/auth-form";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useSession } from "@/hooks/use-session";
import { ADMIN_BACK, ADMIN_REFUSAL, SESSION_LOADING } from "@/lib/copy";
import { AdminFoodsPage } from "./admin-foods-page";

/** Sign-in first, then the administrator check; a parent sees a refusal and no data. */
export function AdminFoodsGate() {
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
  if (!session.user.is_admin) {
    return (
      <main className="flex min-h-dvh items-center justify-center p-4">
        <Card className="w-full max-w-sm">
          <CardContent className="flex flex-col items-start gap-3 pt-6">
            <p className="text-sm" role="alert" data-testid="admin-refusal">
              {ADMIN_REFUSAL}
            </p>
            <Link href="/app" className={buttonVariants({ variant: "outline", size: "sm" })}>
              {ADMIN_BACK}
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }
  return <AdminFoodsPage user={session.user} onSignOut={() => session.signOut.mutate()} />;
}
