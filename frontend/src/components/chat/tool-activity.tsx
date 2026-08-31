"use client";

import {
  CheckIcon,
  ChevronDownIcon,
  CircleDashedIcon,
  LoaderCircleIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  FROM_LOG,
  FROM_PROFILE,
  HIDE_DETAILS,
  SHOW_DETAILS,
  TOOL_CHIP_FAILED,
  TOOL_STEP_PENDING,
  TOOL_STEP_SKIPPED,
  TOOLS_USED,
  toolLabel,
  toolSummary,
} from "@/lib/copy";
import type { ToolStep, ToolStepStatus } from "@/lib/tool-steps";

// Arguments that came from the feeding log rather than the child's details (change 2).
const LOG_ARGS = new Set(["entries", "logged_today", "gaps"]);
const NEUTRAL_ARGS = new Set(["timezone"]);

export function ToolActivityList({ steps, streaming }: { steps: ToolStep[]; streaming: boolean }) {
  // Open while work is happening or something failed; collapsed once a clean answer lands.
  // The parent's own toggle always wins.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  if (steps.length === 0) return null;
  const anyFailed = steps.some((s) => s.status === "error");
  const open = userOpen ?? (streaming || anyFailed);
  return (
    <section className="mt-2" aria-label={TOOLS_USED}>
      <Collapsible open={open} onOpenChange={setUserOpen}>
        <CollapsibleTrigger className="group flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ChevronDownIcon
            className="size-3.5 -rotate-90 transition-transform group-data-panel-open:rotate-0"
            aria-hidden="true"
          />
          {TOOLS_USED}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <TooltipProvider>
            <ul className="mt-1 space-y-1">
              {steps.map((step, i) => (
                <ToolStepRow key={`${step.name}-${i}`} step={step} />
              ))}
            </ul>
          </TooltipProvider>
        </CollapsibleContent>
      </Collapsible>
    </section>
  );
}

function ToolStepRow({ step }: { step: ToolStep }) {
  const [showRaw, setShowRaw] = useState(false);
  const activity = step.activity;
  const failed = step.status === "error";
  const settled = step.status === "ok" || failed;
  const summary = settled
    ? toolSummary(step.name, activity?.args ?? {}, activity?.result ?? null)
    : null;
  const fromLog = activity?.used_context.some((f) => LOG_ARGS.has(f)) ?? false;
  const fromProfile =
    activity?.used_context.some((f) => !LOG_ARGS.has(f) && !NEUTRAL_ARGS.has(f)) ?? false;
  return (
    <li className="max-w-full text-sm" data-testid="tool-chip" data-status={step.status}>
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
        <StepIcon status={step.status} />
        <span className={failed ? "font-medium text-destructive" : "font-medium"}>
          {failed ? `${TOOL_CHIP_FAILED} — ${toolLabel(step.name)}` : toolLabel(step.name)}
        </span>
        {summary && <span className="text-muted-foreground">{summary}</span>}
        {step.status === "skipped" && (
          <span className="text-muted-foreground">{TOOL_STEP_SKIPPED}</span>
        )}
        {activity && fromProfile && (
          <ContextBadge label={FROM_PROFILE} fields={activity.used_context} />
        )}
        {activity && fromLog && <ContextBadge label={FROM_LOG} fields={activity.used_context} />}
        {activity && (
          <Button
            variant="link"
            size="sm"
            className="h-auto px-1 py-0 text-xs"
            onClick={() => setShowRaw((o) => !o)}
          >
            {showRaw ? HIDE_DETAILS : SHOW_DETAILS}
          </Button>
        )}
      </div>
      {failed && activity?.error && <p className="mt-1 pl-5 text-sm">{activity.error}</p>}
      {showRaw && activity && (
        <pre className="mt-1 ml-5 max-h-64 overflow-auto rounded-md bg-muted p-2 text-xs">
          {JSON.stringify(
            failed
              ? { args: activity.args, detail: activity.detail }
              : { args: activity.args, result: activity.result },
            null,
            2,
          )}
        </pre>
      )}
    </li>
  );
}

function StepIcon({ status }: { status: ToolStepStatus }) {
  if (status === "pending") {
    return (
      <>
        <LoaderCircleIcon className="size-3.5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">{TOOL_STEP_PENDING}</span>
      </>
    );
  }
  if (status === "error") {
    return <TriangleAlertIcon className="size-3.5 text-destructive" aria-hidden="true" />;
  }
  if (status === "skipped") {
    return <CircleDashedIcon className="size-3.5 text-muted-foreground" aria-hidden="true" />;
  }
  return <CheckIcon className="size-3.5 text-primary" aria-hidden="true" />;
}

function ContextBadge({ label, fields }: { label: string; fields: string[] }) {
  return (
    <Tooltip>
      <TooltipTrigger className="rounded-full">
        <Badge variant="secondary">{label}</Badge>
      </TooltipTrigger>
      <TooltipContent>{fields.join(", ")}</TooltipContent>
    </Tooltip>
  );
}
