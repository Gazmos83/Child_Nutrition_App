"use client";

import Link from "next/link";
import { useState } from "react";
import { FoodForm } from "@/components/admin/food-form";
import { FoodTable } from "@/components/admin/food-table";
import { ImportPanel } from "@/components/admin/import-panel";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAdminFoods } from "@/hooks/use-admin-foods";
import { ApiError } from "@/lib/api";
import type { CurrentUser, FoodItem, FoodWrite } from "@/lib/api-types";
import * as copy from "@/lib/copy";

interface Props {
  user: CurrentUser;
  onSignOut: () => void;
}

/** null: no form open; a FoodItem: editing it; "new": creating. */
type Editing = null | "new" | FoodItem;

function detailOf(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.status === 409 && !error.detail ? copy.ADMIN_TABLE_CHANGED : error.detail || fallback;
  return fallback;
}

export function AdminFoodsPage({ user, onSignOut }: Props) {
  const admin = useAdminFoods(true);
  const [editing, setEditing] = useState<Editing>(null);
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const save = async (value: FoodWrite) => {
    setSaving(true);
    setServerError(null);
    try {
      if (editing === "new") await admin.create(value);
      else await admin.update(value);
      setEditing(null);
    } catch (e) {
      setServerError(detailOf(e, copy.ADMIN_WRITE_FAILED));
    } finally {
      setSaving(false);
    }
  };
  const toggleActive = async (food: FoodItem) => {
    setBusyId(food.id);
    setRowError(null);
    try {
      await admin.setActive({ id: food.id, active: !food.is_active });
    } catch (e) {
      setRowError(detailOf(e, copy.ADMIN_WRITE_FAILED));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg leading-none text-tomato">{copy.ADMIN_TITLE}</h1>
          <Link href="/app" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            {copy.ADMIN_BACK}
          </Link>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="truncate" data-testid="account-email">
            {user.email}
          </span>
          <Button type="button" variant="ghost" size="sm" onClick={onSignOut}>
            {copy.SIGN_OUT}
          </Button>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-4">
        <p className="text-sm text-muted-foreground">{copy.ADMIN_INTRO}</p>
        {!admin.hydrated && (
          <p className="text-sm text-muted-foreground" role="status">
            {copy.ADMIN_LOADING}
          </p>
        )}
        {admin.unavailable && (
          <p className="text-sm text-destructive" role="alert">
            {copy.ADMIN_UNAVAILABLE}
          </p>
        )}
        {admin.table && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm" data-testid="table-status">
                {copy.adminTableStatus(admin.table.version, admin.table.foods.length)}
              </p>
              <Button
                type="button"
                size="sm"
                disabled={editing !== null}
                onClick={() => {
                  setServerError(null);
                  setEditing("new");
                }}
              >
                {copy.ADMIN_ADD_FOOD}
              </Button>
            </div>
            {editing !== null && (
              <Card>
                <CardContent className="pt-6">
                  <FoodForm
                    key={editing === "new" ? "new" : editing.id}
                    initial={editing === "new" ? null : editing}
                    busy={saving}
                    serverError={serverError}
                    onSubmit={save}
                    onCancel={() => {
                      setEditing(null);
                      setServerError(null);
                    }}
                  />
                </CardContent>
              </Card>
            )}
            {rowError && (
              <p className="text-sm text-destructive" role="alert">
                {rowError}
              </p>
            )}
            <FoodTable
              foods={admin.table.foods}
              busyId={busyId}
              onEdit={(food) => {
                setServerError(null);
                setEditing(food);
              }}
              onToggleActive={toggleActive}
            />
            <Card>
              <CardContent className="pt-6">
                <ImportPanel onImport={admin.importFile} />
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
