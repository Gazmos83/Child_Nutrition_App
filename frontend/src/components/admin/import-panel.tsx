"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import type { FoodImportRequest, FoodImportResult } from "@/lib/api-types";
import * as copy from "@/lib/copy";

/** Mirrors backend/nutrition/food_admin.py:IMPORT_MAX_BYTES. */
export const IMPORT_MAX_BYTES = 1_048_576;

type Mode = FoodImportRequest["mode"] & string;
type Format = FoodImportRequest["format"];

interface Props {
  onImport: (request: FoodImportRequest) => Promise<FoodImportResult>;
}

function formatFor(name: string): Format {
  return name.toLowerCase().endsWith(".csv") ? "csv" : "yaml";
}

/** File in, dry run first, import only after a clean check (design Decision 6). */
export function ImportPanel({ onImport }: Props) {
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [mode, setMode] = useState<Mode>("upsert");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<FoodImportResult | null>(null);
  const [applied, setApplied] = useState<FoodImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setPreview(null);
    setApplied(null);
    setError(null);
  };
  const pick = (input: HTMLInputElement) => {
    reset();
    const chosen = input.files?.[0];
    if (!chosen) {
      setFile(null);
      return;
    }
    if (chosen.size > IMPORT_MAX_BYTES) {
      setFile(null);
      setError(copy.ADMIN_IMPORT_TOO_LARGE);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setFile({ name: chosen.name, content: String(reader.result ?? "") });
    reader.readAsText(chosen);
  };
  const run = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await onImport({
        format: formatFor(file.name),
        content: file.content,
        mode,
        dry_run: dryRun,
      });
      if (dryRun) setPreview(result);
      else setApplied(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : copy.ADMIN_IMPORT_UNREADABLE);
    } finally {
      setBusy(false);
    }
  };

  const changes = preview ? preview.created.length + preview.updated.length : 0;
  const canApply = preview !== null && preview.errors.length === 0 && changes > 0 && applied === null;

  return (
    <section className="flex flex-col gap-3" data-testid="import-panel">
      <h3 className="text-base font-medium">{copy.ADMIN_IMPORT_TITLE}</h3>
      <p className="text-sm text-muted-foreground">{copy.ADMIN_IMPORT_INTRO}</p>
      <div className="flex flex-col gap-1">
        <label htmlFor="import-file" className="text-sm font-medium">
          {copy.ADMIN_IMPORT_FILE}
        </label>
        <input
          id="import-file"
          type="file"
          accept=".yaml,.yml,.csv,text/csv,text/yaml"
          className="text-sm"
          onChange={(e) => pick(e.currentTarget)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span id="import-mode-label" className="text-sm">
          {copy.ADMIN_IMPORT_MODE}
        </span>
        <div role="radiogroup" aria-labelledby="import-mode-label" className="flex gap-1">
          {(
            [
              ["upsert", copy.ADMIN_IMPORT_MODE_UPSERT],
              ["create_only", copy.ADMIN_IMPORT_MODE_CREATE_ONLY],
            ] as const
          ).map(([value, label]) => (
            <Button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              variant={mode === value ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setMode(value);
                reset();
              }}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline" disabled={!file || busy} onClick={() => run(true)}>
          {busy ? copy.ADMIN_IMPORT_WORKING : copy.ADMIN_IMPORT_CHECK}
        </Button>
        <Button type="button" disabled={!canApply || busy} onClick={() => run(false)}>
          {copy.ADMIN_IMPORT_APPLY}
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      {applied ? (
        <div className="flex flex-col gap-1 text-sm" role="status" data-testid="import-applied">
          <p className="font-medium">{copy.ADMIN_IMPORT_APPLIED}</p>
          <p>{copy.adminImportCounts(applied.created.length, applied.updated.length, applied.unchanged.length)}</p>
          <p className="text-muted-foreground">{copy.adminTableStatus(applied.version, applied.created.length + applied.updated.length + applied.unchanged.length)}</p>
        </div>
      ) : (
        preview && (
          <div className="flex flex-col gap-2 text-sm" role="status" data-testid="import-preview">
            <p className="font-medium">
              {preview.errors.length > 0 ? copy.ADMIN_IMPORT_ERRORS_INTRO : copy.ADMIN_IMPORT_NOTHING_WRITTEN}
            </p>
            <p>{copy.adminImportCounts(preview.created.length, preview.updated.length, preview.unchanged.length)}</p>
            {preview.errors.length === 0 && changes === 0 && (
              <p className="text-muted-foreground">{copy.ADMIN_IMPORT_NO_CHANGES}</p>
            )}
            {preview.errors.length > 0 && (
              <div>
                <p className="font-medium">{copy.ADMIN_IMPORT_ERRORS}</p>
                <ul className="list-disc pl-5" data-testid="import-errors">
                  {preview.errors.map((err, i) => (
                    <li key={`${err.row}-${err.field ?? ""}-${i}`}>
                      {copy.importRowError(err.row, err.id, err.field, err.message)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )
      )}
    </section>
  );
}
