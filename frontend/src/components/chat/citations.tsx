"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api-types";
import { HIDE_PASSAGE, SHOW_PASSAGE, SOURCES_TITLE } from "@/lib/copy";

function headline(c: Citation): string {
  const year = c.year ? ` (${c.year})` : "";
  const descriptors = [c.topic, c.section].filter(Boolean).join(", ");
  return `${c.source}${year}${descriptors ? ` — ${descriptors}` : ""}`;
}

export function Citations({ citations, messageId }: { citations: Citation[]; messageId: string }) {
  if (citations.length === 0) return null;
  return (
    <section className="mt-3 text-sm" aria-label={SOURCES_TITLE}>
      <h4 className="mb-1 font-medium">{SOURCES_TITLE}</h4>
      <ol className="space-y-1">
        {citations.map((c) => (
          <CitationItem key={c.index} citation={c} messageId={messageId} />
        ))}
      </ol>
    </section>
  );
}

function CitationItem({ citation, messageId }: { citation: Citation; messageId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li id={`src-${messageId}-${citation.index}`} className="scroll-mt-4">
      <span className="mr-1 tabular-nums text-muted-foreground">[{citation.index}]</span>
      <span>{headline(citation)}</span>
      <Button variant="link" size="sm" className="h-auto px-1 py-0" onClick={() => setOpen((o) => !o)}>
        {open ? HIDE_PASSAGE : SHOW_PASSAGE}
      </Button>
      {open && (
        <blockquote className="mt-1 border-l-2 pl-3 text-muted-foreground">{citation.excerpt}</blockquote>
      )}
    </li>
  );
}
