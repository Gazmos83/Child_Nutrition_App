import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useChildContext } from "@/hooks/use-child-context";
import { dailyTargetsKey } from "@/hooks/use-daily-targets";
import { useGrowthLog } from "@/hooks/use-growth-log";
import { fetchJson } from "@/lib/api";
import type { GrowthIndicatorResult, GrowthMeasurement } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { curvesFixture } from "@/lib/__tests__/fixtures/growth-curves";
import { GrowthTab } from "../growth-tab";

const PROFILE = {
  id: "c1",
  birth_date: "2026-01-10",
  age_months: 7,
  weight_kg: 8.7,
  sex: "female",
  height_cm: 70,
  diet_preference: "omnivore",
  allergies: [],
  notes: [],
  activity_level: "low_active",
  created_at: "2026-08-27T09:00:00Z",
};

function indicator(overrides: Partial<GrowthIndicatorResult>): GrowthIndicatorResult {
  return {
    indicator: "weight_for_age",
    measurement: 8.7,
    unit: "kg",
    z_score: 0.55,
    percentile: 70.9,
    band: "expected",
    who_label: null,
    reference: { sd2neg: 6.3, median: 7.9, sd2pos: 10.2 },
    ...overrides,
  };
}

const NEWER: GrowthMeasurement = {
  id: "m2",
  measured_on: "2026-09-02",
  age_months: 7,
  age_months_exact: 7.7,
  weight_kg: 8.7,
  height_cm: 70,
  assessment: {
    age_months: 7,
    sex: "female",
    weight_kg: 8.7,
    height_cm: 70,
    indicators: [
      indicator({}),
      indicator({ indicator: "length_height_for_age", measurement: 70, unit: "cm" }),
      indicator({ indicator: "weight_for_length_height" }),
      indicator({ indicator: "bmi_for_age", measurement: 17.8, unit: "kg/m²" }),
    ],
    skipped: [],
    source: "WHO Child Growth Standards (2006)",
    source_url: "https://www.who.int/tools/child-growth-standards/standards",
    note: "Compared by completed month (month 7).",
  },
  created_at: "2026-09-02T09:00:00Z",
};

const OLDER: GrowthMeasurement = {
  id: "m1",
  measured_on: "2026-08-02",
  age_months: 6,
  age_months_exact: 6.7,
  weight_kg: 8.2,
  height_cm: null,
  assessment: {
    ...NEWER.assessment!,
    age_months: 6,
    weight_kg: 8.2,
    height_cm: null,
    indicators: [indicator({ measurement: 8.2 })],
    skipped: [
      { indicator: "length_height_for_age", reason: "needs height" },
      { indicator: "weight_for_length_height", reason: "needs height" },
      { indicator: "bmi_for_age", reason: "needs height" },
    ],
  },
  created_at: "2026-08-02T09:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Drives the real hooks over a mocked fetch; counts calls per URL to prove invalidation. */
function renderTab(
  measurements: GrowthMeasurement[],
  profile: typeof PROFILE | null = PROFILE,
  curvesStatus = 200,
) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (url.endsWith("/api/children")) return Promise.resolve(jsonResponse(profile ? [profile] : []));
    if (url.endsWith("/targets")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/growth/curves")) {
      return Promise.resolve(
        curvesStatus === 200 ? jsonResponse(curvesFixture(7)) : jsonResponse({ detail: "down" }, curvesStatus),
      );
    }
    if (url.endsWith("/growth") && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as { measured_on: string; weight_kg: number };
      return Promise.resolve(
        jsonResponse({ ...NEWER, id: "m3", measured_on: body.measured_on, weight_kg: body.weight_kg }, 201),
      );
    }
    if (url.endsWith("/growth")) return Promise.resolve(jsonResponse(measurements));
    if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
    return Promise.resolve(jsonResponse({ detail: "unexpected" }, 500));
  });

  function Harness() {
    const ctx = useChildContext();
    const growth = useGrowthLog(ctx.childId);
    // The daily-targets panel is one of the readers a new measurement must refresh.
    useQuery({
      queryKey: dailyTargetsKey(ctx.childId),
      queryFn: () => fetchJson(`/api/children/${ctx.childId}/targets`),
      enabled: ctx.childId !== null,
    });
    return <GrowthTab growth={growth} birthDate={ctx.profile?.birth_date ?? null} />;
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  const count = (prefix: string) => calls.filter((c) => c.startsWith(prefix)).length;
  return { calls, count };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GrowthTab", () => {
  it("asks for the child first and fetches no measurements without one", async () => {
    const { calls } = renderTab([], null);
    expect(await screen.findByTestId("growth-needs-child")).toHaveTextContent(copy.GROWTH_NEEDS_CHILD);
    await waitFor(() => expect(calls.some((c) => c.endsWith("/api/children"))).toBe(true));
    expect(calls.some((c) => c.endsWith("/growth"))).toBe(false);
  });

  it("invites the first measurement when the list is empty", async () => {
    renderTab([]);
    expect(await screen.findByTestId("growth-empty")).toHaveTextContent(copy.GROWTH_EMPTY);
    expect(screen.getByRole("form", { name: copy.GROWTH_ADD_TITLE })).toBeInTheDocument();
  });

  it("lists measurements newest first with a percentile row per indicator", async () => {
    const { container } = { container: document.body, ...renderTab([OLDER, NEWER]) };
    const entries = await screen.findAllByTestId("growth-entry");
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent(copy.measurementLine(8.7, 70));
    expect(entries[0]).toHaveTextContent(copy.monthsOld(7));
    expect(entries[1]).toHaveTextContent(copy.measurementLine(8.2, null));
    expect(container.querySelectorAll("[data-slot='progress-track']")).toHaveLength(5);
    expect(screen.getAllByTestId("growth-entry-no-height")).toHaveLength(1);
    expect(screen.getAllByText(copy.GROWTH_SOURCE_LINE)).toHaveLength(1);
    expect(screen.getAllByText(copy.GROWTH_TREND_NOTE)).toHaveLength(1);
  });

  it("draws the four charts above the list once curves arrive, and none without measurements", async () => {
    renderTab([OLDER, NEWER]);
    await screen.findByTestId("growth-charts");
    expect(screen.getAllByTestId("growth-chart")).toHaveLength(4);
    expect(screen.getAllByTestId("percentile-curve")).toHaveLength(36);
    const charts = screen.getByTestId("growth-charts");
    const list = screen.getByTestId("growth-entries");
    expect(charts.compareDocumentPosition(list)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("shows no chart for a child without measurements", async () => {
    renderTab([]);
    await screen.findByTestId("growth-empty");
    expect(screen.queryByTestId("growth-charts")).toBeNull();
  });

  it("keeps the list when the curves cannot be loaded", async () => {
    renderTab([OLDER, NEWER], PROFILE, 500);
    expect(await screen.findByTestId("growth-charts-unavailable")).toHaveTextContent(
      copy.GROWTH_CHARTS_UNAVAILABLE,
    );
    expect(screen.getAllByTestId("growth-entry")).toHaveLength(2);
    expect(screen.queryByTestId("growth-charts")).toBeNull();
  });

  it("removing a measurement deletes it and refreshes the profile and targets", async () => {
    const { count } = renderTab([OLDER, NEWER]);
    await screen.findAllByTestId("growth-entry");
    await waitFor(() => expect(count("GET /api/children/c1/targets")).toBe(1));
    const childrenReads = count("GET /api/children");
    fireEvent.click(screen.getAllByRole("button", { name: copy.LOG_DELETE })[0]);
    await waitFor(() => expect(screen.getAllByTestId("growth-entry")).toHaveLength(1));
    expect(count("DELETE /api/children/c1/growth/m2")).toBe(1);
    await waitFor(() => expect(count("GET /api/children/c1/targets")).toBe(2));
    await waitFor(() => expect(count("GET /api/children")).toBeGreaterThan(childrenReads));
  });

  it("adding a measurement prepends it and refreshes the profile and targets", async () => {
    const { count } = renderTab([OLDER]);
    await screen.findAllByTestId("growth-entry");
    await waitFor(() => expect(count("GET /api/children/c1/targets")).toBe(1));
    fireEvent.change(screen.getByLabelText(copy.FORM_WEIGHT_LABEL), { target: { value: "8.9" } });
    fireEvent.click(screen.getByRole("button", { name: copy.GROWTH_ADD }));
    await waitFor(() => expect(screen.getAllByTestId("growth-entry")).toHaveLength(2));
    expect(screen.getAllByTestId("growth-entry")[0]).toHaveTextContent(copy.measurementLine(8.9, 70));
    expect(await screen.findByRole("status")).toHaveTextContent(copy.GROWTH_LOGGED);
    expect(count("POST /api/children/c1/growth")).toBe(1);
    await waitFor(() => expect(count("GET /api/children/c1/targets")).toBe(2));
  });
});
