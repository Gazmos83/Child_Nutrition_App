## Context

See proposal.md — Why. Relevant current state (after `growth-tracking`):

- `backend/nutrition/growth.py` holds the LMS arithmetic: `_sd(t, L, M, S)` is already the
  inverse — the measurement value at z = t — and `percentile(z)` uses
  `statistics.NormalDist`. `LoadedGrowthTable.monthly(indicator, sex, month)` gives L, M, S
  for the three monthly indicators over 0–60; the weight-for-length/height data is two
  0.1 cm tables (`length` 45–110 cm, `height` 65–120 cm) reachable through
  `weight_for_lh(sex, age, cm)` / `weight_for_lh_range(sex, age)`, with the table chosen by
  `age < 24`. `get_growth_table()` is the cached accessor.
- `GET /api/children/{id}/growth` returns `GrowthMeasurementResponse` rows (`measured_on`,
  `age_months`, `weight_kg`, `height_cm`, `assessment`); `to_growth_response` builds them.
  `tests/test_app.py::USER_SCOPED_PATHS` pins the route surface.
- Frontend: `hooks/use-growth-log.ts` (list, add, remove; invalidates children and
  daily-targets), `components/side-panel/growth-tab.tsx` (form, list, notes),
  `components/chat/growth-card.tsx` exports `GrowthIndicatorRow`; theme tokens in
  `app/globals.css` include `--tomato` (accent), `--foreground`, `--muted-foreground`,
  `--border`, and neutral `--chart-1…5`; the dark theme redefines them. No charting
  dependency; `copy.ts` snapshot test forbids prose literals in components.
- The dataviz guidance that applies: one series (the child) needs no legend box, reference
  curves are annotation not series, 2 px line and ≥ 8 px markers with a 2 px surface ring,
  selective direct labels, recessive grid, text in text tokens, a hover layer by default,
  a table view (the list) present, dark mode from tokens not an automatic flip.

## Goals / Non-Goals

**Goals:**
- Every plotted reference value is produced by the existing arithmetic in `backend/nutrition`
  and cached once per (sex, table); the browser only draws.
- Four charts that read as one system: same axes treatment, same curve styling, same marker,
  same tooltip; legible at the tab's width on desktop and stacked on a phone.
- Zero new dependency; the component is testable with jsdom by counting SVG elements.

**Non-Goals:**
- Anything under proposal.md — Non-goals. No zoom, no export, no z-score curves.

## Decisions

### 1. Curves come from the backend, sampled once per (sex, table), not from LMS in the browser

**Decision:** `backend/nutrition/growth.py` gains `value_at_percentile(p, L, M, S)` =
`_sd(NormalDist().inv_cdf(p / 100), L, M, S)` and `reference_curves(table, sex,
use_height_table) -> GrowthCurves` that samples the three monthly indicators at months
0–60 and weight-for-length/height at every whole centimetre of the chosen table, for
percentiles 10, 20, …, 90; values rounded like the assessment (one decimal; BMI two).
Cached with `functools.lru_cache` on `(sex, use_height_table)` in a small wrapper, since
the table is immutable for the process. The route reads the child only for `sex` and
`age_months < 24`.

**Why:** The architecture principle puts every number in Python; shipping L, M, S to the
browser and inverting there would move growth arithmetic into TypeScript, duplicating the
tail rules and the rounding. Whole-centimetre sampling keeps the payload small (≈ 66 or 56
points × 9 curves) while the 0.1 cm table stays the assessment's source. Percentiles
10–90 sit within ±1.29 SD, so WHO's tail adjustment (beyond ±3 SD) never applies to a
curve value.

**Alternative:** embed the curves in the list response — rejected: they change with sex and
the 24-month table switch, not with measurements, and would be resent on every list read.

### 2. Response shape: shared x-values per indicator, one value array per percentile

**Decision:** `GrowthCurvesResponse { sex, age_months, indicators: [GrowthCurveSet], source,
source_url }` with `GrowthCurveSet { indicator, x_unit: "months" | "cm", x_label_table:
"length" | "height" | null, y_unit, xs: [float], curves: [{ percentile: int, values:
[float] }] }`, `len(values) == len(xs)` enforced by a validator.

**Why:** The chart draws each curve as one polyline over the same x positions; a shared
`xs` avoids repeating x nine times and makes "values are ordered across percentiles at
every x" a one-line test. `x_label_table` lets the chart say which table it shows.

### 3. Exact age for the x-axis comes from the server as `age_months_exact`

**Decision:** `GrowthMeasurementResponse.age_months_exact = round(days_since_birth /
30.4375, 2)` alongside the integer `age_months`. The assessment keeps using completed
months. `0.0` when the measurement is on or before the birth date (the out-of-range case
that already yields `assessment=None`).

**Why:** Two weigh-ins ten days apart in the same completed month must not stack on one x.
Computing it server-side keeps date arithmetic out of the browser and next to the other
age logic. It is still an age in months (hard rule 1); the fraction exists for the axis
only, and the field name says so.

**Alternative:** plot at completed months — rejected: a week-old newborn and a 3-week-old
would share x = 0 while their weights differ by half a kilo.

### 4. Inline SVG, one `GrowthChart` component, four instances

**Decision:** `components/side-panel/growth-charts.tsx` exports `GrowthCharts({ measurements,
curves, ageMonths })` laying out four `GrowthChart` cards in a responsive grid, and
`GrowthChart({ set, points, xDomain, title, caption })`. Scales are plain linear functions
over a fixed `viewBox` (e.g. 320 × 220 with 36/12/28/40 px margins); `preserveAspectRatio`
lets it stretch to the card width. No library.

**Why:** Four small line charts with nine static curves are under a hundred lines of SVG; a
charting dependency would add tens of kilobytes and a second styling system for one tab.
Fixed `viewBox` scaling keeps geometry deterministic in jsdom, so tests can count paths and
markers.

### 5. Domains and point selection

**Decision:** Age charts: x from 0 to 24 when the child's current age is under 24 months,
else 0 to 60; the curves' `xs` are filtered to the domain. Weight-for-length/height: x is
the set's `xs` range. y domain: the min of the 10th curve and the max of the 90th over the
domain, extended to include every plotted point, padded 5 %, ticks at "nice" steps.
Points per chart: weight-for-age → every measurement, x = `age_months_exact`, y = weight;
length/height-for-age → measurements with a height, y = height; BMI-for-age → measurements
whose assessment has a `bmi_for_age` indicator, y = that indicator's `measurement`;
weight-for-length/height → measurements with a height, x = height, y = weight. A point's
percentile for the tooltip comes from the matching indicator in `assessment.indicators`
(absent when skipped — the tooltip then shows date and value only).

**Why:** WHO's own charts are 0–2 and 2–5 years; a 7-month-old on a 0–60 axis is a dot in
the corner. Taking y from the curves plus the points keeps an outlier visible rather than
clipped. Using the assessment's own indicator values (BMI, percentile) means the chart
never recomputes a number the server already produced.

### 6. Styling: reference curves as annotation, the child as the one series

**Decision:** Percentile curves: `stroke: var(--color-muted-foreground)`, `stroke-width`
1, opacity 0.55; the 50th: `stroke: var(--color-foreground)`, width 2, full opacity.
Direct labels at the right end of the 10th, 50th, and 90th curves ("10th", "50th", "90th"
via `copy.percentileLabel`), text in muted ink. Child series: `stroke: var(--color-tomato)`
width 2, `fill: none`; markers `r = 4` (8 px) filled tomato with a 2 px ring in
`var(--color-card)`. Grid: horizontal lines only, `var(--color-border)`, 1 px. Axis text
`text-[10px]` muted. Tooltip: React state on marker hover/focus renders a small `<g>` with a
`<rect>` in `var(--color-card)` and `<text>` in foreground ink, positioned to stay inside
the plot; each marker is focusable (`tabIndex=0`, `aria-label` with date, value, percentile)
so keyboard users get the same. Charts carry `role="img"` and an `aria-label` naming the
indicator and the child's sex; the list below is the table view.

**Why:** One series means no categorical palette and no legend box (the dataviz rules); the
curves are context and should recede, with only the median pulled forward as the user
asked. Every colour is a theme token, so the dark theme is the tokens' dark values rather
than an inverted image, and text never wears the series colour. Labelling only three of
nine curves avoids the collisions the BMI curves would produce where they bunch.

### 7. Data flow and caching in the UI

**Decision:** `useGrowthCurves(childId)` in `hooks/use-growth-log.ts`: query key
`["growth-curves", childId]`, `enabled` with a child, `staleTime: Infinity` (curves change
only when the profile's sex or 24-month bucket changes). `use-child-context.ts` invalidates
`["growth-curves"]` on save and removes it on clear; sign-out and the 401 handler remove it
with the other account caches. `GrowthTab` renders `GrowthCharts` when `measurements.length
> 0`; while curves load it renders nothing in their place; on curve error it shows
`GROWTH_CHARTS_UNAVAILABLE` and the list still renders.

**Why:** Same shape as the other account-scoped queries; the failure mode degrades to the
existing list rather than blanking the tab.

### 8. Copy

**Decision:** `copy.ts` gains `GROWTH_CHARTS_TITLE`, `GROWTH_CHART_CAPTION` ("Thin lines are
the WHO 10th to 90th percentiles for this sex; the bold line is the 50th"),
`GROWTH_CHARTS_UNAVAILABLE`, `GROWTH_AXIS_AGE` ("Age (months)"), `GROWTH_AXIS_LENGTH_HEIGHT`
("Length/height (cm)"), `growthTableNote(table)` ("Shown on the WHO length table (under 24
months)" / "… height table (from 24 months)"), `percentileLabel(p)` (reuses `ordinal`), and
`chartPointLabel(date, value, unit, percentile | null)` for tooltips and `aria-label`s.
Direct voice; snapshot updated and reviewed.

## Risks / Trade-offs

- [Curve labels collide where curves bunch (BMI, early months)] → only the 10th, 50th, and
  90th are labelled, right-aligned at the domain edge with a small surface halo; the caption
  names the rest.
- [A child straddling 24 months sees older points against the height table] → the chart
  says which table it shows; the per-row bars remain the authoritative per-day reading.
- [Payload size] → whole-centimetre sampling and 0–60 monthly points: roughly 4 × 9 × ≤ 66
  numbers, a few kilobytes, fetched once per profile and cached.
- [jsdom has no layout] → the component computes geometry from the fixed `viewBox`, so
  tests assert on element counts, `data-percentile`, `stroke-width`, and label text, not
  on pixels; the visual pass is the screenshot in the end-to-end task.
- [Percentile ordering assumption] → asserted in the backend test at every x for every
  indicator; the inverse-LMS is monotonic in z for valid L, M, S.

## Migration Plan

Additive: one route, one response field, one component. Apply after `growth-tracking` is
committed. Rollback is removing the route from `children.py` and the `GrowthCharts` render
from the tab; no data changes.
