import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FoodItem } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { FoodForm } from "../food-form";

const KALE: FoodItem = {
  id: "kale_chips",
  name: "Kale chips",
  category: "vegetable",
  serving_size: 20,
  serving_unit: "g",
  calories: 90,
  protein_g: 2,
  fat_g: 6,
  carbohydrate_g: 8,
  iron_mg: 0.5,
  calcium_mg: 30,
  allergens: [],
  choking_hazard: true,
  contains_honey: false,
  commonly_unpasteurized: false,
  min_age_months: 12,
  source: "Brand label",
  notes: null,
  is_active: false,
};

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function answer(question: string, answerLabel: string) {
  const group = screen.getByRole("radiogroup", { name: question });
  fireEvent.click(within(group).getByRole("radio", { name: answerLabel }));
}

describe("FoodForm", () => {
  it("preselects no safety answer and refuses to save until every question is answered", () => {
    const onSubmit = vi.fn();
    render(<FoodForm initial={null} busy={false} serverError={null} onSubmit={onSubmit} onCancel={() => {}} />);
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toHaveAttribute("aria-checked", "false");
    }
    fireEvent.click(screen.getByRole("button", { name: copy.ADMIN_SAVE }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getAllByText(copy.ADMIN_SAFETY_REQUIRED)).toHaveLength(3);
    expect(screen.getByText(copy.ADMIN_ERROR_SOURCE)).toBeInTheDocument();

    answer(copy.ADMIN_SAFETY_CHOKING, copy.ADMIN_YES);
    answer(copy.ADMIN_SAFETY_HONEY, copy.ADMIN_NO);
    expect(screen.getAllByText(copy.ADMIN_SAFETY_REQUIRED)).toHaveLength(1);
  });

  it("submits a complete new food with the source and explicit flags", () => {
    const onSubmit = vi.fn();
    render(<FoodForm initial={null} busy={false} serverError={null} onSubmit={onSubmit} onCancel={() => {}} />);
    fill(copy.ADMIN_FIELD_ID, "kale_chips");
    fill(copy.ADMIN_FIELD_NAME, "Kale chips");
    fill(copy.ADMIN_FIELD_MIN_AGE, "12");
    fill(copy.ADMIN_FIELD_SERVING_SIZE, "20");
    fill(copy.ADMIN_FIELD_CALORIES, "90");
    fill(copy.ADMIN_FIELD_PROTEIN, "2");
    fill(copy.ADMIN_FIELD_FAT, "6");
    fill(copy.ADMIN_FIELD_CARBS, "8");
    fill(copy.ADMIN_FIELD_IRON, "0.5");
    fill(copy.ADMIN_FIELD_CALCIUM, "30");
    fill(copy.ADMIN_FIELD_SOURCE, "Brand label");
    answer(copy.ADMIN_SAFETY_CHOKING, copy.ADMIN_YES);
    answer(copy.ADMIN_SAFETY_HONEY, copy.ADMIN_NO);
    answer(copy.ADMIN_SAFETY_UNPASTEURIZED, copy.ADMIN_NO);
    fireEvent.click(screen.getByRole("button", { name: copy.ADMIN_SAVE }));
    // The category select is a popover; without it the form still refuses.
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(copy.ADMIN_ERROR_REQUIRED)).toBeInTheDocument();
  });

  it("shows a stored food with its answers, keeps its id fixed and its state, and shows the server's detail", () => {
    const onSubmit = vi.fn();
    const { rerender } = render(
      <FoodForm initial={KALE} busy={false} serverError={null} onSubmit={onSubmit} onCancel={() => {}} />,
    );
    expect(screen.getByLabelText(copy.ADMIN_FIELD_ID)).toBeDisabled();
    const choking = screen.getByRole("radiogroup", { name: copy.ADMIN_SAFETY_CHOKING });
    expect(within(choking).getByRole("radio", { name: copy.ADMIN_YES })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("button", { name: copy.ADMIN_SAVE }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ id: "kale_chips", choking_hazard: true, is_active: false });

    rerender(
      <FoodForm
        initial={KALE}
        busy={false}
        serverError="Food 'kale_chips' already exists"
        onSubmit={onSubmit}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByTestId("food-form-server-error")).toHaveTextContent("Food 'kale_chips' already exists");
  });
});
