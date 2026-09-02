import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import type { GrowthMeasurement, GrowthMeasurementWrite } from "@/lib/api-types";
import { todayIsoDate } from "@/lib/child-context-store";
import * as copy from "@/lib/copy";
import { LogMeasurementForm } from "../log-measurement-form";

const BIRTH_DATE = "2026-01-10";

function stored(body: GrowthMeasurementWrite): GrowthMeasurement {
  return {
    id: "m1",
    measured_on: body.measured_on,
    age_months: 7,
    weight_kg: body.weight_kg,
    height_cm: body.height_cm ?? null,
    assessment: null,
    created_at: "2026-09-02T09:00:00Z",
  };
}

function renderForm(post?: (body: GrowthMeasurementWrite) => Promise<GrowthMeasurement>) {
  const submit = vi.fn(post ?? ((body: GrowthMeasurementWrite) => Promise.resolve(stored(body))));
  const onLogged = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <LogMeasurementForm birthDate={BIRTH_DATE} submit={submit} onLogged={onLogged} />
    </QueryClientProvider>,
  );
  return { submit, onLogged };
}

function fill(fields: { date?: string; weight?: string; height?: string }) {
  if (fields.date !== undefined) {
    fireEvent.change(screen.getByLabelText(copy.GROWTH_DATE_LABEL), { target: { value: fields.date } });
  }
  if (fields.weight !== undefined) {
    fireEvent.change(screen.getByLabelText(copy.FORM_WEIGHT_LABEL), { target: { value: fields.weight } });
  }
  if (fields.height !== undefined) {
    fireEvent.change(screen.getByLabelText(copy.FORM_HEIGHT_LABEL, { exact: false }), {
      target: { value: fields.height },
    });
  }
}

function add() {
  fireEvent.click(screen.getByRole("button", { name: copy.GROWTH_ADD }));
}

describe("LogMeasurementForm", () => {
  it("defaults the date to today and bounds it to the birth date", () => {
    renderForm();
    const date = screen.getByLabelText(copy.GROWTH_DATE_LABEL) as HTMLInputElement;
    expect(date.value).toBe(todayIsoDate());
    expect(date.max).toBe(todayIsoDate());
    expect(date.min).toBe(BIRTH_DATE);
  });

  it("posts a weight-only measurement with a null height", async () => {
    const { submit, onLogged } = renderForm();
    fill({ weight: "8.5" });
    add();
    await waitFor(() => expect(onLogged).toHaveBeenCalled());
    expect(submit.mock.calls[0][0]).toEqual({
      measured_on: todayIsoDate(),
      weight_kg: 8.5,
      height_cm: null,
    });
    expect((screen.getByLabelText(copy.FORM_WEIGHT_LABEL) as HTMLInputElement).value).toBe("");
  });

  it("posts the height when given", async () => {
    const { submit } = renderForm();
    fill({ date: "2026-05-10", weight: "7.2", height: "66" });
    add();
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(submit.mock.calls[0][0]).toEqual({ measured_on: "2026-05-10", weight_kg: 7.2, height_cm: 66 });
  });

  it("refuses a non-positive weight before posting", async () => {
    const { submit } = renderForm();
    fill({ weight: "0" });
    add();
    expect(await screen.findByRole("alert")).toHaveTextContent(copy.FORM_ERROR_WEIGHT);
    expect(submit).not.toHaveBeenCalled();
  });

  it("refuses a date before the birth date", async () => {
    const { submit } = renderForm();
    fill({ date: "2026-01-09", weight: "3.5" });
    add();
    expect(await screen.findByRole("alert")).toHaveTextContent(copy.GROWTH_ERROR_DATE);
    expect(submit).not.toHaveBeenCalled();
  });

  it("shows the server's own reason on a 422 or 409, and the generic line otherwise", async () => {
    renderForm(() => Promise.reject(new ApiError(409, "A measurement for that day already exists")));
    fill({ weight: "8.5" });
    add();
    expect(await screen.findByRole("alert")).toHaveTextContent("A measurement for that day already exists");
    expect((screen.getByLabelText(copy.FORM_WEIGHT_LABEL) as HTMLInputElement).value).toBe("8.5");
  });

  it("falls back to the generic line on other failures", async () => {
    renderForm(() => Promise.reject(new Error("network")));
    fill({ weight: "8.5" });
    add();
    expect(await screen.findByRole("alert")).toHaveTextContent(copy.GROWTH_ADD_FAILED);
  });
});
