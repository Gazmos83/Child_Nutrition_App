import { describe, expect, it } from "vitest";
import { parseSseFrames } from "../sse";

const frame = (event: string, data: unknown) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

describe("parseSseFrames", () => {
  it("parses several frames in one chunk", () => {
    const { events, carry } = parseSseFrames(
      frame("route", { intent: "tool", planned: ["calculate_bmi"] }) +
        frame("token", { text: "Hi " }) +
        frame("done", {}),
    );
    expect(events.map((e) => e.event)).toEqual(["route", "token", "done"]);
    expect(events[0]).toEqual({ event: "route", data: { intent: "tool", planned: ["calculate_bmi"] } });
    expect(carry).toBe("");
  });

  it("carries a frame split across two chunks", () => {
    const whole = frame("token", { text: "split across" });
    const cut = 17;
    const first = parseSseFrames(whole.slice(0, cut));
    expect(first.events).toEqual([]);
    expect(first.carry).toBe(whole.slice(0, cut));
    const second = parseSseFrames(whole.slice(cut), first.carry);
    expect(second.events).toEqual([{ event: "token", data: { text: "split across" } }]);
    expect(second.carry).toBe("");
  });

  it("keeps a trailing partial frame as carry", () => {
    const { events, carry } = parseSseFrames(frame("token", { text: "a" }) + "event: tok");
    expect(events).toHaveLength(1);
    expect(carry).toBe("event: tok");
  });

  it("accepts CRLF line endings and multi-line data", () => {
    const { events } = parseSseFrames('event: token\r\ndata: {"text":\r\ndata: "x"}\r\n\r\n');
    expect(events).toEqual([{ event: "token", data: { text: "x" } }]);
  });

  it("drops frames without an event name or with bad JSON", () => {
    const { events } = parseSseFrames('data: {"x":1}\n\nevent: token\ndata: {oops\n\n');
    expect(events).toEqual([]);
  });
});
