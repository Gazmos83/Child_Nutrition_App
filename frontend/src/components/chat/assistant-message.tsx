"use client";

import { Button } from "@/components/ui/button";
import { isGrowthAssessmentResult, isMealPlanResult, isNutrientGapReport } from "@/lib/api-types";
import type { AssistantMessage as AssistantMessageData } from "@/lib/chat-reducer";
import * as copy from "@/lib/copy";
import { toolSteps } from "@/lib/tool-steps";
import { AnswerText } from "./answer-text";
import { Citations } from "./citations";
import { Disclaimer } from "./disclaimer";
import { ExternalFoodCard } from "./external-food-card";
import { GapReportCard } from "./gap-report-card";
import { GrowthCard } from "./growth-card";
import { IntentChip } from "./intent-chip";
import { MealPlanCard } from "./meal-plan-card";
import { ToolActivityList } from "./tool-activity";

export function AssistantMessage({
  message,
  isAdmin,
  onRetry,
  retryDisabled,
}: {
  message: AssistantMessageData;
  isAdmin: boolean;
  onRetry: (id: string) => void;
  retryDisabled: boolean;
}) {
  const plan = message.tools
    .filter((t) => t.name === "generate_meal_plan" && t.status === "ok")
    .map((t) => t.result as unknown)
    .find(isMealPlanResult);
  const gapReport = message.tools
    .filter((t) => t.name === "detect_nutrient_gaps" && t.status === "ok")
    .map((t) => t.result as unknown)
    .find(isNutrientGapReport);
  const growth = message.tools
    .filter((t) => t.name === "assess_growth" && t.status === "ok")
    .map((t) => t.result as unknown)
    .find(isGrowthAssessmentResult);
  const externalLookups = message.tools
    .map((t) => t.external_lookup)
    .filter((c): c is NonNullable<typeof c> => Boolean(c));
  const streaming = message.status === "streaming";
  const troubled = message.status === "error" || message.status === "interrupted";

  return (
    <article className="ink-outline rounded-lg bg-card p-4 text-card-foreground" data-status={message.status}>
      <div className="flex flex-wrap items-center gap-2">
        <IntentChip intent={message.intent} />
        {streaming && (
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {copy.THINKING}
          </span>
        )}
      </div>
      <ToolActivityList steps={toolSteps(message)} streaming={streaming} />
      {growth && <GrowthCard result={growth} />}
      {gapReport && <GapReportCard report={gapReport} />}
      {plan && <MealPlanCard plan={plan} />}
      {message.text && (
        <div className="mt-3">
          <AnswerText text={message.text} messageId={message.id} />
        </div>
      )}
      {troubled && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm" role="alert">
          <p className="mb-2 font-medium">{copy.INCOMPLETE}</p>
          <p>{message.error}</p>
          <Button className="mt-2" size="sm" variant="outline" disabled={retryDisabled} onClick={() => onRetry(message.id)}>
            {copy.RETRY}
          </Button>
        </div>
      )}
      {externalLookups.map((citation, i) => (
        <ExternalFoodCard key={`${citation.source_key}-${citation.query}-${i}`} citation={citation} isAdmin={isAdmin} />
      ))}
      <Citations citations={message.citations} messageId={message.id} />
      {(message.text || troubled || message.status === "done") && <Disclaimer text={message.disclaimer} />}
    </article>
  );
}
