// Renders answer text with `[n]` citation markers as superscript anchors to the Sources list.

const MARKER = /\[(\d+)\]/g;

export function AnswerText({ text, messageId }: { text: string; messageId: string }) {
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
  return <div className="whitespace-pre-wrap leading-relaxed">{parts}</div>;
}
