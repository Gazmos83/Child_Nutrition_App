import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptyAssistantMessage } from "@/lib/chat-reducer";
import * as copy from "@/lib/copy";
import { AssistantMessage } from "../assistant-message";

vi.mock("@/hooks/use-admin-foods", () => ({
  useAdminFoods: () => ({ create: vi.fn() }),
}));

const CITATION = {
  query: "kumquat",
  matched_name: "Kumquat, raw",
  source_key: "usda_fdc" as const,
  source_label: "USDA FoodData Central",
  source_url: "https://fdc.nal.usda.gov/food-details/123",
  retrieved_at: "2026-09-03T00:00:00Z",
  serving_description: "per 100 g",
  nutrients: {
    calories: 71,
    protein_g: 1.9,
    fat_g: 0.9,
    carbohydrate_g: 15.9,
    iron_mg: 0.86,
    calcium_mg: 62,
  },
  admin_approval_eligible: false,
  disclaimer: "This is third-party nutrition data, not one of our reviewed pediatric sources",
};

describe("AssistantMessage — external lookup card", () => {
  it("renders the card alongside a failed lookup without triggering the troubled banner", () => {
    const message = {
      ...emptyAssistantMessage("a1"),
      status: "done" as const,
      text: "",
      tools: [
        {
          name: "lookup_food",
          status: "error" as const,
          args: { food_id: "kumquat" },
          used_context: [],
          result: null,
          error: 'We don’t know a food called “kumquat” yet',
          detail: "Unknown food id 'kumquat'",
          external_lookup: CITATION,
        },
      ],
    };
    render(<AssistantMessage message={message} isAdmin={false} onRetry={() => {}} retryDisabled={false} />);
    expect(screen.getByText(copy.EXTERNAL_FOOD_TITLE)).toBeInTheDocument();
    expect(screen.getByText("Kumquat, raw")).toBeInTheDocument();
    expect(screen.queryByText(copy.INCOMPLETE)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not render a card when no tool activity carries an external lookup", () => {
    const message = { ...emptyAssistantMessage("a2"), status: "done" as const, text: "Around 11 mg a day" };
    render(<AssistantMessage message={message} isAdmin={false} onRetry={() => {}} retryDisabled={false} />);
    expect(screen.queryByText(copy.EXTERNAL_FOOD_TITLE)).toBeNull();
  });
});
