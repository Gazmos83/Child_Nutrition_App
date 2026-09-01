import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import type { GrowthAssessmentResult, GrowthIndicatorResult } from "@/lib/api-types";
import * as copy from "@/lib/copy";

/** Where a z-score sits on the −3…+3 track, as a percentage of its width. */
function trackPosition(z: number): number {
  const clamped = Math.max(-3, Math.min(3, z));
  return ((clamped + 3) / 6) * 100;
}

function IndicatorRow({ indicator }: { indicator: GrowthIndicatorResult }) {
  const label = copy.GROWTH_INDICATOR_LABELS[indicator.indicator] ?? indicator.indicator;
  return (
    <li data-testid="growth-row" data-band={indicator.band}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{label}</span>
        <Badge variant="outline">{copy.GROWTH_BAND_LABELS[indicator.band]}</Badge>
      </div>
      <p className="tabular-nums">
        {copy.formatNumber(indicator.measurement)} {indicator.unit} —{" "}
        {copy.ordinal(indicator.percentile)} percentile
      </p>
      <Progress
        value={trackPosition(indicator.z_score)}
        max={100}
        aria-label={label}
        className="mt-1"
      >
        <ProgressTrack>
          <ProgressIndicator />
        </ProgressTrack>
      </Progress>
      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
        {copy.growthReference(
          indicator.reference.sd2neg,
          indicator.reference.median,
          indicator.reference.sd2pos,
          indicator.unit,
        )}
      </p>
      {indicator.who_label && (
        <p className="mt-1 text-sm" data-testid="growth-who-label">
          {copy.growthWhoLabel(indicator.who_label)}
        </p>
      )}
    </li>
  );
}

export function GrowthCard({ result }: { result: GrowthAssessmentResult }) {
  return (
    <Card className="ink-outline mt-3" data-testid="growth-card">
      <CardHeader>
        <CardTitle>{copy.GROWTH_TITLE}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ul className="space-y-3">
          {result.indicators.map((indicator) => (
            <IndicatorRow key={indicator.indicator} indicator={indicator} />
          ))}
          {result.skipped.map((skipped) => (
            <li key={skipped.indicator} data-testid="growth-skipped">
              <div className="mb-1 font-medium">
                {copy.GROWTH_INDICATOR_LABELS[skipped.indicator] ?? skipped.indicator}
              </div>
              <p className="text-muted-foreground">{skipped.reason}</p>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">{copy.GROWTH_SOURCE_LINE}</p>
        <p className="text-xs text-muted-foreground">{copy.GROWTH_TREND_NOTE}</p>
      </CardContent>
    </Card>
  );
}
