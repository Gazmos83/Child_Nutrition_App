import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExternalFoodCitation } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { ExternalFoodCard } from "../external-food-card";

const create = vi.fn();
vi.mock("@/hooks/use-admin-foods", () => ({
  useAdminFoods: () => ({ create }),
}));

const CITATION: ExternalFoodCitation = {
  query: "kumquat",
  matched_name: "Kumquat, raw",
  source_key: "usda_fdc",
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
  admin_approval_eligible: true,
  disclaimer: "This is third-party nutrition data, not one of our reviewed pediatric sources",
};

describe("ExternalFoodCard", () => {
  beforeEach(() => create.mockReset());

  it("shows the match, nutrients, source, and disclaimer, visibly apart from citations", () => {
    render(<ExternalFoodCard citation={CITATION} isAdmin={false} />);
    expect(screen.getByText(copy.EXTERNAL_FOOD_TITLE)).toBeInTheDocument();
    expect(screen.getByText("Kumquat, raw")).toBeInTheDocument();
    expect(screen.getByText(CITATION.disclaimer)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "USDA FoodData Central" })).toHaveAttribute(
      "href",
      CITATION.source_url,
    );
    expect(screen.getByText(/71 kcal/)).toBeInTheDocument();
  });

  it("never offers approval to a non-admin, even when the citation is eligible", () => {
    render(<ExternalFoodCard citation={CITATION} isAdmin={false} />);
    expect(screen.queryByRole("button", { name: copy.EXTERNAL_FOOD_ADD })).toBeNull();
  });

  it("never offers approval when the citation itself is not eligible, even to an admin", () => {
    render(<ExternalFoodCard citation={{ ...CITATION, admin_approval_eligible: false }} isAdmin={true} />);
    expect(screen.queryByRole("button", { name: copy.EXTERNAL_FOOD_ADD })).toBeNull();
  });

  it("lets an eligible admin expand a form prefilled from the citation, and cancel out of it", () => {
    render(<ExternalFoodCard citation={CITATION} isAdmin={true} />);
    const addButton = screen.getByRole("button", { name: copy.EXTERNAL_FOOD_ADD });
    fireEvent.click(addButton);

    // Nutrients and name come from the citation; safety fields stay unanswered (design
    // Decision 8) -- nothing about safety may be fetched or guessed.
    expect(screen.getByLabelText(copy.ADMIN_FIELD_NAME)).toHaveValue("Kumquat, raw");
    expect(screen.getByLabelText(copy.ADMIN_FIELD_CALORIES)).toHaveValue(71);
    expect(screen.getByLabelText(copy.ADMIN_FIELD_PROTEIN)).toHaveValue(1.9);
    expect((screen.getByLabelText(copy.ADMIN_FIELD_SOURCE) as HTMLInputElement).value).toContain(
      "USDA FoodData Central",
    );
    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toHaveAttribute("aria-checked", "false");
    }

    fireEvent.click(screen.getByRole("button", { name: copy.ADMIN_CANCEL }));
    expect(screen.queryByLabelText(copy.ADMIN_FIELD_NAME)).toBeNull();
    expect(screen.getByRole("button", { name: copy.EXTERNAL_FOOD_ADD })).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });
});
