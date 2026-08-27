"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ToolActivity as ToolActivityData } from "@/lib/api-types";
import { FROM_LOG, FROM_PROFILE, HIDE_DETAILS, SHOW_DETAILS, TOOL_CHIP_FAILED, TOOLS_USED, toolLabel } from "@/lib/copy";

// Arguments that came from the feeding log rather than the child's details (change 2).
const LOG_ARGS = new Set(["entries", "logged_today", "gaps"]);
const NEUTRAL_ARGS = new Set(["timezone"]);

export function ToolActivityList({ tools }: { tools: ToolActivityData[] }) {
  if (tools.length === 0) return null;
  return (
    <section className="mt-2" aria-label={TOOLS_USED}>
      <ul className="flex flex-wrap gap-2">
        {tools.map((t, i) => (
          <ToolChip key={`${t.name}-${i}`} tool={t} />
        ))}
      </ul>
    </section>
  );
}

function ToolChip({ tool }: { tool: ToolActivityData }) {
  const [open, setOpen] = useState(false);
  const failed = tool.status === "error";
  const fromLog = tool.used_context.some((f) => LOG_ARGS.has(f));
  const fromProfile = tool.used_context.some((f) => !LOG_ARGS.has(f) && !NEUTRAL_ARGS.has(f));
  return (
    <li className="max-w-full" data-testid="tool-chip" data-status={tool.status}>
      <div className="flex flex-wrap items-center gap-1">
        <Badge variant={failed ? "destructive" : "outline"}>
          <span aria-hidden="true">{failed ? "✗" : "✓"}</span>
          <span>{failed ? `${TOOL_CHIP_FAILED} — ${toolLabel(tool.name)}` : toolLabel(tool.name)}</span>
        </Badge>
        {fromProfile && (
          <Badge variant="secondary" title={tool.used_context.join(", ")}>
            {FROM_PROFILE}
          </Badge>
        )}
        {fromLog && (
          <Badge variant="secondary" title={tool.used_context.join(", ")}>
            {FROM_LOG}
          </Badge>
        )}
        <Button variant="link" size="sm" className="h-auto px-1 py-0 text-xs" onClick={() => setOpen((o) => !o)}>
          {open ? HIDE_DETAILS : SHOW_DETAILS}
        </Button>
      </div>
      {failed && tool.error && <p className="mt-1 text-sm">{tool.error}</p>}
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-muted p-2 text-xs">
          {JSON.stringify(failed ? { args: tool.args, detail: tool.detail } : { args: tool.args, result: tool.result }, null, 2)}
        </pre>
      )}
    </li>
  );
}
