import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useChildContext } from "@/hooks/use-child-context";
import type { DailyTargetsResponse, NutrientTargetRow } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { DailyTargets } from "../daily-targets";

function targetRow(overrides: Partial<NutrientTargetRow>): NutrientTargetRow {
  return {
    nutrient: "calories",
    label: "Calories",
    unit: "kcal",
    amount: 678,
    reference_type: "EER",
    band: "7–12 months",
    source: "NIH DRI (2005)",
    upper_limit: null,
    tracked: true,
    derivation: "",
    per_kg: null,
    activity_level: null,
    advisory: null,
    advisory_source_date: null,
    display_note: "",
    not_tracked_reason: null,
    intake_average: null,
    ratio: null,
    flag: null,
    ...overrides,
  };
}

const VITAMIN_D_REASON =
  "Vitamin D mostly comes from a supplement and sunshine, not from logged food, so we show the target without a score.";

// A 9-month omnivore's set, in the server's order: iron promoted ahead of protein.
const OMNIVORE: DailyTargetsResponse = {
  targets: {
    calories: { calories: 678, band: "7–12 months", formula: "EER", activity_level: null, source: "NIH DRI (2005)" },
    protein: { protein_g: 10.2, grams_per_kg: 1.2, reference_type: "RDA", band: "7–12 months", source: "NIH DRI (2005)" },
    iron: { iron_mg: 11, reference_type: "RDA", band: "7–12 months", source: "NIH DRI (2001)" },
    items: [
      targetRow({}),
      targetRow({ nutrient: "iron", label: "Iron", unit: "mg", amount: 11, reference_type: "RDA", flag: "below", ratio: 0.56, intake_average: 6.2 }),
      targetRow({ nutrient: "protein", label: "Protein", unit: "g", amount: 10.2, reference_type: "RDA", per_kg: 1.2 }),
      targetRow({ nutrient: "vitamin_d", label: "Vitamin D", unit: "IU", amount: 400, reference_type: "AI", tracked: false, not_tracked_reason: VITAMIN_D_REASON }),
      targetRow({ nutrient: "zinc", label: "Zinc", unit: "mg", amount: 3, reference_type: "RDA", tracked: false, not_tracked_reason: "We don't have zinc values for these foods yet, so we show the target without a score." }),
      targetRow({ nutrient: "calcium", label: "Calcium", unit: "mg", amount: 260, reference_type: "AI" }),
    ],
  },
  diet_preference: "omnivore",
  doctors_note_present: false,
  disclaimer: copy.DISCLAIMER_FALLBACK,
};

const B12_NOTE =
  "Every vegan child needs a reliable vitamin B12 source — a supplement or fortified foods. Please raise it with your pediatrician.";

const VEGAN: DailyTargetsResponse = {
  ...OMNIVORE,
  targets: {
    ...OMNIVORE.targets,
    items: [
      targetRow({ band: "13–35 months", amount: 992 }),
      targetRow({ nutrient: "protein", label: "Protein", unit: "g", amount: 13.7, reference_type: "RDA", per_kg: 1.05, band: "1–3 years" }),
      targetRow({ nutrient: "vitamin_b12", label: "Vitamin B12", unit: "µg", amount: 0.9, reference_type: "RDA", band: "1–3 years", tracked: false, not_tracked_reason: "We can't count vitamin B12 from logged foods yet, so we show the target without a score.", display_note: B12_NOTE }),
      targetRow({ nutrient: "iron", label: "Iron", unit: "mg", amount: 7, reference_type: "RDA", band: "1–3 years" }),
      targetRow({ nutrient: "calcium", label: "Calcium", unit: "mg", amount: 700, reference_type: "RDA", band: "1–3 years" }),
      targetRow({ nutrient: "dha", label: "Omega-3 (DHA)", unit: "mg", amount: null, reference_type: null, band: "", advisory: "Omega-3 DHA supports brain and eye development. A DHA supplement from algal oil may be worth discussing with your pediatrician.", advisory_source_date: "2020", tracked: false, source: "AAP Pediatric Nutrition (2020)" }),
    ],
  },
  diet_preference: "vegan",
  doctors_note_present: true,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPanel(response: DailyTargetsResponse | null, dirty = false) {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() => Promise.resolve(jsonResponse(response)));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <DailyTargets childId={response ? "c1" : null} dirty={dirty} />
    </QueryClientProvider>,
  );
  return { fetchMock, client, ...view };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DailyTargets", () => {
  it("renders the 9-month omnivore's six rows in server order, without B12", async () => {
    renderPanel(OMNIVORE);
    const rows = await screen.findAllByTestId("target-row");
    expect(rows).toHaveLength(6);
    expect(screen.getByText("Iron").compareDocumentPosition(screen.getByText("Protein"))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(screen.queryByText("Vitamin B12")).toBeNull();
    expect(screen.getByText(copy.targetValue(678, "kcal"))).toBeInTheDocument();
    expect(screen.getByText(copy.DISCLAIMER_FALLBACK)).toBeInTheDocument();
    expect(screen.queryByTestId("targets-note-on-file")).toBeNull();
  });

  it("draws exactly one progress track per tracked row and none elsewhere", async () => {
    const { container } = renderPanel(OMNIVORE);
    await screen.findAllByTestId("target-row");
    // calories, iron, protein, calcium are tracked; vitamin D and zinc are not.
    expect(container.querySelectorAll('[data-slot="progress-track"]')).toHaveLength(4);
    expect(screen.getByText(copy.FLAG_LABELS.below)).toBeInTheDocument();
  });

  it("shows vitamin D's reason and no score", async () => {
    renderPanel(OMNIVORE);
    await screen.findAllByTestId("target-row");
    expect(screen.getByText(VITAMIN_D_REASON)).toBeInTheDocument();
    const vitaminD = screen.getByText("Vitamin D").closest("li");
    expect(vitaminD?.getAttribute("data-kind")).toBe("display-only");
    expect(vitaminD?.querySelector('[data-slot="progress-track"]')).toBeNull();
  });

  it("renders the vegan set: unscored B12 with guidance, DHA advisory with no value", async () => {
    renderPanel(VEGAN);
    await screen.findAllByTestId("target-row");
    const b12 = screen.getByText("Vitamin B12").closest("li");
    expect(b12?.getAttribute("data-kind")).toBe("display-only");
    expect(b12?.querySelector('[data-slot="progress-track"]')).toBeNull();
    expect(screen.getByText(B12_NOTE)).toBeInTheDocument();
    const dha = screen.getByText("Omega-3 (DHA)").closest("li");
    expect(dha?.getAttribute("data-kind")).toBe("advisory");
    expect(dha?.textContent).not.toContain("a day");
    expect(screen.getByText(copy.advisoryFrom("AAP Pediatric Nutrition (2020)", "2020"))).toBeInTheDocument();
    expect(screen.getByTestId("targets-note-on-file")).toHaveTextContent(copy.TARGETS_NOTE_ON_FILE);
  });

  it("explains itself with no saved child, showing no numbers and fetching nothing", () => {
    const { fetchMock } = renderPanel(null);
    expect(screen.getByText(copy.TARGETS_NEEDS_CHILD)).toBeInTheDocument();
    expect(screen.queryAllByTestId("target-row")).toHaveLength(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("hides the numbers behind the save-first hint while the form is dirty", async () => {
    renderPanel(OMNIVORE, true);
    expect(screen.getByTestId("targets-save-first")).toHaveTextContent(copy.TARGETS_SAVE_FIRST);
    expect(screen.queryAllByTestId("target-row")).toHaveLength(0);
  });

  it("refetches after a profile save", async () => {
    const profile = {
      id: "c1",
      birth_date: "2025-11-27",
      age_months: 9,
      weight_kg: 8.5,
      sex: "female",
      height_cm: null,
      diet_preference: "omnivore",
      allergies: [],
      doctors_note: null,
      doctors_note_recorded_at: null,
      activity_level: "low_active",
      created_at: "2026-08-27T09:00:00Z",
    };
    const targetsCalls: string[] = [];
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/targets")) {
          targetsCalls.push(url);
          return Promise.resolve(jsonResponse(OMNIVORE));
        }
        if (init?.method === "PUT") return Promise.resolve(jsonResponse(profile));
        return Promise.resolve(jsonResponse([profile]));
      });
    function Harness() {
      const ctx = useChildContext();
      return (
        <>
          <button type="button" onClick={ctx.save} disabled={!ctx.hydrated}>
            save
          </button>
          <DailyTargets childId={ctx.childId} dirty={ctx.dirty} />
        </>
      );
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Harness />
      </QueryClientProvider>,
    );
    await screen.findAllByTestId("target-row");
    expect(targetsCalls).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => expect(targetsCalls).toHaveLength(2));
    expect(fetchMock).toHaveBeenCalled();
  });
});
