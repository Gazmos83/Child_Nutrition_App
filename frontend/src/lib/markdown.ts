// A tiny block parser for exactly what the answer prompts ask the model for
// (backend/rag/prompts.py, backend/chat/prompts.py: short paragraphs, bulleted lists):
// paragraphs, `-`/`*`/`1.` lists, inline **bold** and `code`. It emits a typed tree —
// no HTML is ever constructed — and it is total on partial input, so a half-streamed
// `**bold` or a bare `- ` renders as plain text and resolves on the next token.

export type InlineNode =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "code"; text: string };

export type Block =
  | { kind: "paragraph"; spans: InlineNode[] }
  | { kind: "list"; ordered: boolean; items: InlineNode[][] };

// Markers need content after them, so a dangling "- " mid-stream stays a paragraph.
const UL_ITEM = /^\s*[-*]\s+(\S.*)$/;
const OL_ITEM = /^\s*\d+\.\s+(\S.*)$/;
const INLINE = /\*\*([^*]+?)\*\*|`([^`]+?)`/g;

export function parseInline(text: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const start = match.index;
    if (start > last) nodes.push({ kind: "text", text: text.slice(last, start) });
    if (match[1] !== undefined) nodes.push({ kind: "bold", text: match[1] });
    else nodes.push({ kind: "code", text: match[2] });
    last = start + match[0].length;
  }
  if (last < text.length) nodes.push({ kind: "text", text: text.slice(last) });
  return nodes;
}

export function parseMarkdown(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: InlineNode[][] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", spans: parseInline(paragraph.join("\n")) });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push({ kind: "list", ordered: list.ordered, items: list.items });
      list = null;
    }
  };

  for (const line of text.split("\n")) {
    const ul = UL_ITEM.exec(line);
    const ol = ul ? null : OL_ITEM.exec(line);
    if (ul || ol) {
      flushParagraph();
      const ordered = ol !== null;
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(parseInline((ul ?? ol)![1]));
      continue;
    }
    flushList();
    if (line.trim() === "") {
      flushParagraph();
      continue;
    }
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return blocks;
}
