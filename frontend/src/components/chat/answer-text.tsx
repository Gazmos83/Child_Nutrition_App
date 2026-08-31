// Renders answer text as the light markdown the prompts ask for (paragraphs, lists,
// bold, code), with `[n]` citation markers as superscript anchors to the Sources list.
// Citation splitting runs on every leaf text run, so a marker inside a bullet or inside
// bold anchors exactly as it does in a paragraph.

import { parseMarkdown, type InlineNode } from "@/lib/markdown";

const MARKER = /\[(\d+)\]/g;

function withCitations(text: string, messageId: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const start = match.index ?? 0;
    if (start > last) parts.push(text.slice(last, start));
    const n = match[1];
    parts.push(
      <sup key={`${start}-${n}`} className="ml-0.5">
        <a
          href={`#src-${messageId}-${n}`}
          className="text-primary underline-offset-2 hover:underline"
          aria-label={`Source ${n}`}
        >
          [{n}]
        </a>
      </sup>,
    );
    last = start + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function Spans({ spans, messageId }: { spans: InlineNode[]; messageId: string }) {
  return (
    <>
      {spans.map((span, i) =>
        span.kind === "bold" ? (
          <strong key={i} className="font-semibold">
            {withCitations(span.text, messageId)}
          </strong>
        ) : span.kind === "code" ? (
          <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
            {span.text}
          </code>
        ) : (
          <span key={i}>{withCitations(span.text, messageId)}</span>
        ),
      )}
    </>
  );
}

export function AnswerText({ text, messageId }: { text: string; messageId: string }) {
  const blocks = parseMarkdown(text);
  return (
    <div className="space-y-2 leading-relaxed">
      {blocks.map((block, i) =>
        block.kind === "paragraph" ? (
          <p key={i} className="whitespace-pre-wrap">
            <Spans spans={block.spans} messageId={messageId} />
          </p>
        ) : block.ordered ? (
          <ol key={i} className="list-decimal space-y-1 pl-5">
            {block.items.map((item, j) => (
              <li key={j}>
                <Spans spans={item} messageId={messageId} />
              </li>
            ))}
          </ol>
        ) : (
          <ul key={i} className="list-disc space-y-1 pl-5">
            {block.items.map((item, j) => (
              <li key={j}>
                <Spans spans={item} messageId={messageId} />
              </li>
            ))}
          </ul>
        ),
      )}
    </div>
  );
}
