"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { NoteOutcome } from "@/lib/api-types";
import {
  MAX_NOTE_CHARS,
  MAX_NOTES,
  newNoteRow,
  noteRowError,
  type NoteRowDraft,
} from "@/lib/child-context-store";
import * as copy from "@/lib/copy";
import { NOTE_KIND_OPTIONS, type NoteKind } from "@/lib/enums";
import { outcomeFor } from "@/lib/note-outcomes";
import { EnumSelect } from "./child-context-form";

interface Props {
  rows: NoteRowDraft[];
  /** The form-level error for the rows, when any row cannot be saved. */
  error?: string;
  /** What the latest meal plan said about each row; marks a row it could not apply. */
  outcomes: readonly NoteOutcome[];
  onChange: (rows: NoteRowDraft[]) => void;
}

/** "Doctor's note and personal preferences": one instruction per row, each with a kind. */
export function ChildNotesFields({ rows, error, outcomes, onChange }: Props) {
  const update = (key: string, patch: Partial<NoteRowDraft>) =>
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  return (
    <fieldset className="flex flex-col gap-2" data-testid="child-notes">
      <legend className="text-sm font-medium">{copy.FORM_NOTES_LABEL}</legend>
      <p className="text-xs text-muted-foreground">{copy.FORM_NOTES_HINT}</p>
      {rows.length > 0 && (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => {
            const rowError = noteRowError(row, rows);
            const notApplied = outcomeFor(outcomes, row.kind, row.text);
            return (
              <li key={row.key} className="flex flex-col gap-1" data-testid="note-row">
                <div className="flex items-start gap-2">
                  <div className="w-40 shrink-0">
                    <EnumSelect<NoteKind>
                      id={`note-kind-${row.key}`}
                      value={row.kind}
                      options={NOTE_KIND_OPTIONS}
                      onChange={(kind) => kind && update(row.key, { kind })}
                    />
                  </div>
                  <Input
                    aria-label={copy.FORM_NOTE_TEXT_LABEL}
                    maxLength={MAX_NOTE_CHARS}
                    placeholder={copy.FORM_NOTE_PLACEHOLDER}
                    value={row.text}
                    onChange={(e) => update(row.key, { text: e.target.value })}
                    aria-invalid={Boolean(rowError)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
                  >
                    {copy.FORM_NOTES_REMOVE}
                  </Button>
                </div>
                {notApplied && (
                  <Badge variant="outline" data-testid="note-not-applied">
                    {copy.noteNotApplied(notApplied.detail)}
                  </Badge>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={rows.length >= MAX_NOTES}
          onClick={() => onChange([...rows, newNoteRow()])}
        >
          {copy.FORM_NOTES_ADD}
        </Button>
      </div>
    </fieldset>
  );
}
