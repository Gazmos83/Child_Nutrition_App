"use client";

import { useState } from "react";
import type { GrowthCurveSet, GrowthCurvesResponse, GrowthMeasurement } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import {
  type ChartPoint,
  indicesWithin,
  niceTicks,
  pointsFor,
  xDomainFor,
  xTicks,
  yDomain,
} from "@/lib/growth-chart-data";
import { formatMeasuredOn } from "@/lib/growth-log-store";

// A fixed drawing box; the SVG stretches to the card. Geometry is deterministic in tests.
const W = 320;
const H = 220;
const PAD = { top: 14, right: 40, bottom: 30, left: 38 };
const LABELLED_PERCENTILES = new Set([10, 50, 90]);
const ORDER = [
  "weight_for_age",
  "length_height_for_age",
  "weight_for_length_height",
  "bmi_for_age",
] as const;

const MUTED = "var(--color-muted-foreground)";
const INK = "var(--color-foreground)";
const ACCENT = "var(--color-tomato)";
const SURFACE = "var(--color-card)";
const GRID = "var(--color-border)";

interface ChartsProps {
  measurements: GrowthMeasurement[];
  curves: GrowthCurvesResponse;
}

export function GrowthCharts({ measurements, curves }: ChartsProps) {
  const sets = ORDER.map((key) => curves.indicators.find((s) => s.indicator === key)).filter(
    (s): s is GrowthCurveSet => s !== undefined,
  );
  return (
    <section className="flex flex-col gap-2" data-testid="growth-charts" aria-label={copy.GROWTH_CHARTS_TITLE}>
      <h3 className="text-sm font-medium">{copy.GROWTH_CHARTS_TITLE}</h3>
      <p className="text-xs text-muted-foreground">{copy.GROWTH_CHART_CAPTION}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {sets.map((set) => (
          <GrowthChart
            key={set.indicator}
            set={set}
            points={pointsFor(set.indicator, measurements)}
            ageMonths={curves.age_months}
            sex={curves.sex}
          />
        ))}
      </div>
    </section>
  );
}

interface ChartProps {
  set: GrowthCurveSet;
  points: ChartPoint[];
  ageMonths: number;
  sex: "female" | "male";
}

export function GrowthChart({ set, points, ageMonths, sex }: ChartProps) {
  const [active, setActive] = useState<ChartPoint | null>(null);
  const xd = xDomainFor(set, ageMonths);
  const yd = yDomain(set, points, xd);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const sx = (x: number) => PAD.left + ((x - xd[0]) / (xd[1] - xd[0])) * plotW;
  const sy = (y: number) => PAD.top + plotH - ((y - yd[0]) / (yd[1] - yd[0])) * plotH;
  const idx = indicesWithin(set, xd);
  const last = idx[idx.length - 1];
  const curvePath = (values: number[]) =>
    idx.map((i, k) => `${k === 0 ? "M" : "L"}${sx(set.xs[i]).toFixed(1)},${sy(values[i]).toFixed(1)}`).join(" ");
  const title = copy.GROWTH_INDICATOR_LABELS[set.indicator] ?? set.indicator;

  return (
    <figure className="rounded-md border p-2" data-testid="growth-chart" data-indicator={set.indicator}>
      <figcaption className="mb-1 text-sm font-medium">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={copy.chartAriaLabel(title, sex)} className="w-full">
        {niceTicks(yd[0], yd[1]).map((t) => (
          <g key={`y-${t}`}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(t)} y2={sy(t)} stroke={GRID} strokeWidth={1} opacity={0.35} />
            <text x={PAD.left - 4} y={sy(t)} textAnchor="end" dominantBaseline="middle" fontSize={9} fill={MUTED}>
              {t}
            </text>
          </g>
        ))}
        <text x={PAD.left - 4} y={PAD.top - 5} textAnchor="end" fontSize={9} fill={MUTED}>
          {set.y_unit}
        </text>
        {xTicks(xd, set.x_unit).map((t) => (
          <text key={`x-${t}`} x={sx(t)} y={H - PAD.bottom + 12} textAnchor="middle" fontSize={9} fill={MUTED} data-testid="x-tick">
            {t}
          </text>
        ))}
        <text x={PAD.left + plotW / 2} y={H - 4} textAnchor="middle" fontSize={9} fill={MUTED}>
          {set.x_unit === "months" ? copy.GROWTH_AXIS_AGE : copy.GROWTH_AXIS_LENGTH_HEIGHT}
        </text>

        {set.curves.map((curve) => {
          const median = curve.percentile === 50;
          return (
            <path
              key={curve.percentile}
              data-testid="percentile-curve"
              data-percentile={curve.percentile}
              d={curvePath(curve.values)}
              fill="none"
              stroke={median ? INK : MUTED}
              strokeWidth={median ? 2 : 1}
              opacity={median ? 1 : 0.55}
              strokeLinejoin="round"
            />
          );
        })}
        {set.curves
          .filter((curve) => LABELLED_PERCENTILES.has(curve.percentile))
          .map((curve) => (
            <text
              key={`label-${curve.percentile}`}
              data-testid="curve-label"
              x={W - PAD.right + 3}
              y={sy(curve.values[last])}
              dominantBaseline="middle"
              fontSize={9}
              fill={curve.percentile === 50 ? INK : MUTED}
            >
              {copy.percentileLabel(curve.percentile)}
            </text>
          ))}

        {points.length > 1 && (
          <path
            data-testid="child-series"
            d={points.map((p, k) => `${k === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ")}
            fill="none"
            stroke={ACCENT}
            strokeWidth={2}
            strokeLinejoin="round"
          />
        )}
        {points.map((p) => (
          <circle
            key={p.id}
            data-testid="chart-point"
            cx={sx(p.x)}
            cy={sy(p.y)}
            r={4}
            fill={ACCENT}
            stroke={SURFACE}
            strokeWidth={2}
            tabIndex={0}
            aria-label={pointLabel(p)}
            onMouseEnter={() => setActive(p)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(p)}
            onBlur={() => setActive(null)}
          />
        ))}
        {active && <Tooltip point={active} x={sx(active.x)} y={sy(active.y)} />}
      </svg>
      {set.x_label_table && (
        <p className="mt-1 text-xs text-muted-foreground" data-testid="chart-table-note">
          {copy.growthTableNote(set.x_label_table)}
        </p>
      )}
    </figure>
  );
}

function pointLabel(p: ChartPoint): string {
  return copy.chartPointLabel(formatMeasuredOn(p.measured_on), p.y, p.unit, p.percentile);
}

function Tooltip({ point, x, y }: { point: ChartPoint; x: number; y: number }) {
  const label = pointLabel(point);
  const width = label.length * 4.6 + 10;
  const left = Math.min(Math.max(x + 8, PAD.left), W - PAD.right - width);
  const top = Math.max(y - 22, 2);
  return (
    <g data-testid="chart-tooltip" transform={`translate(${left.toFixed(1)}, ${top.toFixed(1)})`} pointerEvents="none">
      <rect width={width} height={16} rx={3} fill={SURFACE} stroke={GRID} />
      <text x={5} y={11} fontSize={9} fill={INK}>
        {label}
      </text>
    </g>
  );
}
