// Server-sent-event parsing for the chat stream. Pure: chunks may split a frame anywhere,
// so the unparsed tail is returned as `carry` and fed back in with the next chunk.

import type { ChatSseEvent } from "./api-types";

export interface ParsedFrames {
  events: ChatSseEvent[];
  carry: string;
}

export function parseSseFrames(chunk: string, carry = ""): ParsedFrames {
  const buffer = (carry + chunk).replace(/\r\n/g, "\n");
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const events: ChatSseEvent[] = [];
  for (const frame of frames) {
    const event = parseFrame(frame);
    if (event) events.push(event);
  }
  return { events, carry: rest };
}

function parseFrame(frame: string): ChatSseEvent | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!event) return null;
  const raw = dataLines.join("\n");
  let data: unknown = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return { event, data } as ChatSseEvent;
}
