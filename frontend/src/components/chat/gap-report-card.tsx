import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import type { GapFlag, NutrientGapReport } from "@/lib/api-types";
import * as copy from "@/lib/copy";
import { OverrideBanner } from "./meal-plan-card";

const FLAG_CLASS: Record<GapFlag, string> = {
  below: "border-amber-400 bg-amber-50 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100",
  adequate: "",
  above: "border-sky-400 bg-sky-50 text-sky-950 dark:bg-sky-950/30 dark:text-sky-100",
};

export function GapReportCard({ report }: { report: NutrientGapReport }) {
  const insufficient = report.status === "insufficient_data";
  const anyBelow = report.gaps.some((g) => g.flag === "below");
  const first = report.gaps[0];
  return (
    <Card className="ink-outline mt-3" data-testid="gap-report-card" data-status={report.status}>
      <CardHeader>
        <CardTitle>{copy.GAPS_TITLE}</CardTitle>
        {!insufficient && report.confidence && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline" data-testid="confidence">
              {copy.CONFIDENCE_LABELS[report.confidence]}
            </Badge>
            <span>{copy.gapsWindow(report.days_logged, report.window_days)}</span>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {report.override?.conflict && <OverrideBanner override={report.override} />}
        {insufficient ? (
          <p>{copy.GAPS_INSUFFICIENT}</p>
        ) : (
          <>
            {report.confidence === "low" && <p className="text-muted-foreground">{copy.GAPS_LOW}</p>}
            <ul className="space-y-3">
              {report.gaps.map((gap) => (
                <li key={gap.nutrient} data-testid="gap-row" data-flag={gap.flag}>
                  <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                    <span>{copy.COVERAGE_LABELS[gap.nutrient]}</span>
                    <Badge variant="outline" className={FLAG_CLASS[gap.flag]}>
                      {copy.FLAG_LABELS[gap.flag]}
                    </Badge>
                  </div>
                  <p className="mb-1 tabular-nums text-muted-foreground">
                    {copy.gapLine(gap.average, gap.target, gap.unit)}
                  </p>
                  <Progress
                    value={Math.min(gap.ratio * 100, 100)}
                    max={100}
                    aria-label={copy.COVERAGE_LABELS[gap.nutrient]}
                  >
                    <ProgressTrack>
                      <ProgressIndicator />
                    </ProgressTrack>
                  </Progress>
                </li>
              ))}
            </ul>
            {anyBelow && <p>{copy.FLAG_BELOW_NOTE}</p>}
            {first && (
              <p className="text-xs text-muted-foreground">
                {copy.targetsFrom(first.target_source, first.target_band)}
              </p>
            )}
          </>
        )}
        {report.partial_days > 0 && (
          <p className="text-muted-foreground" data-testid="partial-days">
            {copy.partialDaysNote(report.partial_days)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
