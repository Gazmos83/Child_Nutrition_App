import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FoodImportRequest, FoodImportResult } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { IMPORT_MAX_BYTES, ImportPanel } from "../import-panel";

const CSV = "id,name\nkale_chips,Kale chips\n";

function result(overrides: Partial<FoodImportResult>): FoodImportResult {
  return {
    applied: false,
    created: [],
    updated: [],
    unchanged: [],
    errors: [],
    version: "db-1",
    revision: 1,
    ...overrides,
  };
}

async function chooseFile(name: string, content: string) {
  const input = screen.getByLabelText(copy.ADMIN_IMPORT_FILE) as HTMLInputElement;
  const file = new File([content], name, { type: "text/csv" });
  await act(async () => {
    fireEvent.change(input, { target: { files: [file] } });
  });
  await waitFor(() => expect(screen.getByRole("button", { name: copy.ADMIN_IMPORT_CHECK })).toBeEnabled());
}

describe("ImportPanel", () => {
  it("dry-runs the file, names each failing row, and keeps the import button disabled", async () => {
    const onImport = vi.fn(async () =>
      result({
        created: ["kale_chips"],
        errors: [{ row: 3, id: "puffs", field: "min_age_months", message: "must be at least 6" }],
      }),
    );
    render(<ImportPanel onImport={onImport} />);
    expect(screen.getByRole("button", { name: copy.ADMIN_IMPORT_CHECK })).toBeDisabled();
    await chooseFile("foods.csv", CSV);
    fireEvent.click(screen.getByRole("button", { name: copy.ADMIN_IMPORT_CHECK }));
    await screen.findByTestId("import-preview");
    expect(onImport).toHaveBeenCalledWith({ format: "csv", content: CSV, mode: "upsert", dry_run: true });
    expect(screen.getByText(copy.ADMIN_IMPORT_ERRORS_INTRO)).toBeInTheDocument();
    expect(screen.getByTestId("import-errors")).toHaveTextContent(
      copy.importRowError(3, "puffs", "min_age_months", "must be at least 6"),
    );
    expect(screen.getByRole("button", { name: copy.ADMIN_IMPORT_APPLY })).toBeDisabled();
  });

  it("imports after a clean check and reports the counts", async () => {
    const onImport = vi.fn(async (req: FoodImportRequest) =>
      result({
        applied: !req.dry_run,
        created: ["kale_chips"],
        updated: ["oatmeal_porridge"],
        unchanged: ["banana"],
        version: req.dry_run ? "db-1" : "db-2",
      }),
    );
    render(<ImportPanel onImport={onImport} />);
    await chooseFile("foods.yaml", "foods: []");
    fireEvent.click(screen.getByRole("radio", { name: copy.ADMIN_IMPORT_MODE_CREATE_ONLY }));
    fireEvent.click(screen.getByRole("button", { name: copy.ADMIN_IMPORT_CHECK }));
    await screen.findByTestId("import-preview");
    expect(screen.getByText(copy.ADMIN_IMPORT_NOTHING_WRITTEN)).toBeInTheDocument();
    expect(screen.getByText(copy.adminImportCounts(1, 1, 1))).toBeInTheDocument();
    const apply = screen.getByRole("button", { name: copy.ADMIN_IMPORT_APPLY });
    expect(apply).toBeEnabled();
    fireEvent.click(apply);
    await screen.findByTestId("import-applied");
    expect(onImport).toHaveBeenLastCalledWith({
      format: "yaml",
      content: "foods: []",
      mode: "create_only",
      dry_run: false,
    });
    expect(screen.getByText(copy.ADMIN_IMPORT_APPLIED)).toBeInTheDocument();
    expect(screen.getByText(copy.adminTableStatus("db-2", 3))).toBeInTheDocument();
  });

  it("refuses a file over the size limit before reading it", async () => {
    const onImport = vi.fn();
    render(<ImportPanel onImport={onImport} />);
    const input = screen.getByLabelText(copy.ADMIN_IMPORT_FILE) as HTMLInputElement;
    const big = new File(["x".repeat(IMPORT_MAX_BYTES + 1)], "big.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [big] } });
    expect(screen.getByRole("alert")).toHaveTextContent(copy.ADMIN_IMPORT_TOO_LARGE);
    expect(screen.getByRole("button", { name: copy.ADMIN_IMPORT_CHECK })).toBeDisabled();
  });
});
