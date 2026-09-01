import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FeedingEntry, FoodSummary, LoggedFeeding } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { LogFeedForm } from "../log-feed-form";

function food(overrides: Partial<FoodSummary>): FoodSummary {
  return {
    id: "carrot_puree",
    name: "Carrot purée",
    category: "vegetable",
    serving_size: 60,
    serving_unit: "g",
    min_age_months: 6,
    ...overrides,
  };
}

const FOODS: FoodSummary[] = [
  food({ id: "breast_milk", name: "Breast milk, mature", category: "milk_feed", serving_unit: "ml" }),
  food({ id: "infant_formula_iron_fortified", name: "Infant formula, iron-fortified", category: "milk_feed", serving_unit: "ml" }),
  food({}),
  food({ id: "apple_puree", name: "Apple purée", category: "fruit" }),
  food({ id: "avocado", name: "Avocado, mashed", category: "fruit" }),
  food({ id: "banana", name: "Banana, mashed", category: "fruit" }),
  food({ id: "oatmeal", name: "Oatmeal porridge", category: "grain" }),
  food({ id: "pasta", name: "Pasta, soft-cooked", category: "grain" }),
  food({ id: "peas", name: "Peas, mashed", category: "vegetable" }),
  food({ id: "lentils", name: "Lentils, soft", category: "legume" }),
];

function logged(entry: FeedingEntry): LoggedFeeding {
  return {
    entry: { ...entry, id: "feed-1" },
    food_id: entry.food_id ?? null,
    food_name: null,
    quantified: entry.quantity != null,
    nutrients: { calories: 0, protein_g: 0, fat_g: 0, carbohydrate_g: 0, iron_mg: 0, calcium_mg: 0 },
    source: "test",
  };
}

function renderForm() {
  const submit = vi.fn((entry: FeedingEntry) => Promise.resolve(logged(entry)));
  const onLogged = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <LogFeedForm foods={FOODS} foodsLoading={false} foodsError={false} submit={submit} onLogged={onLogged} />
    </QueryClientProvider>,
  );
  return { submit, onLogged };
}

function slotButton(label: string): HTMLElement {
  return screen.getByRole("radio", { name: label });
}

/** Type into the search box; `inputType` marks it as real typing, not autofill. */
function searchFoods(query: string): HTMLElement {
  const input = screen.getByPlaceholderText(copy.LOG_FOOD_SEARCH_PLACEHOLDER);
  fireEvent.focus(input);
  fireEvent.input(input, { target: { value: query }, inputType: "insertText" });
  return input;
}

async function pickFood(query: string, optionName: RegExp) {
  const input = searchFoods(query);
  const option = await screen.findByRole("option", { name: optionName });
  fireEvent.click(option);
  return input;
}

function addFeed() {
  fireEvent.click(screen.getByRole("button", { name: copy.LOG_ADD }));
}

describe("LogFeedForm", () => {
  it("defaults to Breastfed: no food picker, blank amount allowed, breast milk posted", async () => {
    const { submit } = renderForm();
    expect(slotButton("Breastfed")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByPlaceholderText(copy.LOG_FOOD_SEARCH_PLACEHOLDER)).toBeNull();
    addFeed();
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][0]).toMatchObject({
      feeding_type: "breastmilk",
      food_id: "breast_milk",
      quantity: null,
      unit: "ml",
    });
  });

  it("derives a solid feed with the food's unit and the slot's local time", async () => {
    const { submit, onLogged } = renderForm();
    fireEvent.click(slotButton("Lunch"));
    await pickFood("carr", /Carrot/);
    fireEvent.change(screen.getByLabelText(/How much/), { target: { value: "60" } });
    addFeed();
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    const entry = submit.mock.calls[0][0];
    expect(entry).toMatchObject({
      feeding_type: "solid",
      food_id: "carrot_puree",
      quantity: 60,
      unit: "g",
    });
    const when = new Date(entry.fed_at);
    expect([when.getHours(), when.getMinutes()]).toEqual([12, 30]);
    const today = new Date();
    expect(when.getDate()).toBe(today.getDate());
    await waitFor(() => expect(onLogged).toHaveBeenCalledOnce());
  });

  it("derives formula from a formula pick, always in ml", async () => {
    const { submit } = renderForm();
    fireEvent.click(slotButton("Breakfast"));
    await pickFood("formula", /Infant formula/);
    fireEvent.change(screen.getByLabelText(/How much/), { target: { value: "120" } });
    addFeed();
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    const entry = submit.mock.calls[0][0];
    expect(entry).toMatchObject({ feeding_type: "formula", food_id: "infant_formula_iron_fortified", unit: "ml" });
    expect(new Date(entry.fed_at).getHours()).toBe(8);
  });

  it("offers Water in the search and posts it with no food id", async () => {
    const { submit } = renderForm();
    fireEvent.click(slotButton("Snack"));
    await pickFood("wat", /Water/);
    fireEvent.change(screen.getByLabelText(/How much/), { target: { value: "50" } });
    addFeed();
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][0]).toMatchObject({
      feeding_type: "water",
      food_id: null,
      quantity: 50,
      unit: "ml",
    });
  });

  it("shows at most 7 suggestions", async () => {
    renderForm();
    fireEvent.click(slotButton("Dinner"));
    searchFoods("a");
    const options = await screen.findAllByRole("option");
    expect(FOODS.filter((f) => f.name.toLowerCase().includes("a")).length).toBeGreaterThan(7);
    expect(options.length).toBeLessThanOrEqual(7);
  });

  it("asks for a food when none is picked, and for an amount when it is not breast milk", async () => {
    const { submit } = renderForm();
    fireEvent.click(slotButton("Dinner"));
    addFeed();
    expect(await screen.findByRole("alert")).toHaveTextContent(copy.LOG_ERROR_FOOD);
    await pickFood("peas", /Peas/);
    addFeed();
    expect(await screen.findByRole("alert")).toHaveTextContent(copy.LOG_ERROR_QUANTITY);
    expect(submit).not.toHaveBeenCalled();
  });
});
