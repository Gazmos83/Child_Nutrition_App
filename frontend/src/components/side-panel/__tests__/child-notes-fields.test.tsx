import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { NoteOutcome } from "@/lib/api-types";
import type { NoteRowDraft } from "@/lib/child-context-store";
import * as copy from "@/lib/copy";
import { ChildNotesFields } from "../child-notes-fields";

function Harness({ initial, outcomes = [] }: { initial: NoteRowDraft[]; outcomes?: NoteOutcome[] }) {
  const [rows, setRows] = useState(initial);
  return <ChildNotesFields rows={rows} outcomes={outcomes} onChange={setRows} />;
}

describe("ChildNotesFields", () => {
  it("adds a preference row, edits it, and removes it", () => {
    render(<Harness initial={[]} />);
    expect(screen.getByText(copy.FORM_NOTES_LABEL)).toBeInTheDocument();
    expect(screen.queryAllByTestId("note-row")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: copy.FORM_NOTES_ADD }));
    expect(screen.getAllByTestId("note-row")).toHaveLength(1);
    const input = screen.getByLabelText(copy.FORM_NOTE_TEXT_LABEL) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "no pork" } });
    expect(input.value).toBe("no pork");
    fireEvent.click(screen.getByRole("button", { name: copy.FORM_NOTES_REMOVE }));
    expect(screen.queryAllByTestId("note-row")).toHaveLength(0);
  });

  it("marks a row the last plan could not apply, and clears the mark once edited", () => {
    const outcomes: NoteOutcome[] = [
      { index: 0, kind: "preference", text: "no kale chips", applied: false, detail: "not in our table" },
    ];
    render(
      <Harness initial={[{ key: "k1", kind: "preference", text: "no kale chips" }]} outcomes={outcomes} />,
    );
    expect(screen.getByTestId("note-not-applied")).toHaveTextContent(copy.noteNotApplied("not in our table"));
    fireEvent.change(screen.getByLabelText(copy.FORM_NOTE_TEXT_LABEL), { target: { value: "no kale" } });
    expect(screen.queryByTestId("note-not-applied")).toBeNull();
  });

  it("shows the rows error and disables adding past the cap", () => {
    const rows = Array.from({ length: 20 }, (_, i) => ({ key: `k${i}`, kind: "preference" as const, text: `row ${i}` }));
    render(<ChildNotesFields rows={rows} error={copy.FORM_ERROR_NOTE} outcomes={[]} onChange={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent(copy.FORM_ERROR_NOTE);
    expect(screen.getByRole("button", { name: copy.FORM_NOTES_ADD })).toBeDisabled();
  });
});
