import { describe, expect, it } from "vitest";
import { parseInline, parseMarkdown } from "../markdown";

describe("parseInline", () => {
  it("splits bold and code out of plain text", () => {
    expect(parseInline("Iron is **important** — try `oatmeal` daily")).toEqual([
      { kind: "text", text: "Iron is " },
      { kind: "bold", text: "important" },
      { kind: "text", text: " — try " },
      { kind: "code", text: "oatmeal" },
      { kind: "text", text: " daily" },
    ]);
  });

  it("leaves an unclosed marker as plain text while it streams", () => {
    expect(parseInline("this is **bold")).toEqual([{ kind: "text", text: "this is **bold" }]);
    expect(parseInline("and `code")).toEqual([{ kind: "text", text: "and `code" }]);
  });

  it("returns nothing for an empty string", () => {
    expect(parseInline("")).toEqual([]);
  });
});

describe("parseMarkdown", () => {
  it("splits paragraphs on blank lines and keeps single line breaks inside one", () => {
    expect(parseMarkdown("First thought.\nStill the first.\n\nSecond thought.")).toEqual([
      { kind: "paragraph", spans: [{ kind: "text", text: "First thought.\nStill the first." }] },
      { kind: "paragraph", spans: [{ kind: "text", text: "Second thought." }] },
    ]);
  });

  it("collects - and * lines into one unordered list", () => {
    const blocks = parseMarkdown("Good first foods:\n- oatmeal\n* mashed banana\n- lentils");
    expect(blocks).toHaveLength(2);
    expect(blocks[1]).toEqual({
      kind: "list",
      ordered: false,
      items: [
        [{ kind: "text", text: "oatmeal" }],
        [{ kind: "text", text: "mashed banana" }],
        [{ kind: "text", text: "lentils" }],
      ],
    });
  });

  it("collects numbered lines into an ordered list, separate from bullets", () => {
    const blocks = parseMarkdown("1. wash hands\n2. mash the banana\n- a bullet");
    expect(blocks).toEqual([
      {
        kind: "list",
        ordered: true,
        items: [[{ kind: "text", text: "wash hands" }], [{ kind: "text", text: "mash the banana" }]],
      },
      { kind: "list", ordered: false, items: [[{ kind: "text", text: "a bullet" }]] },
    ]);
  });

  it("parses inline bold inside a list item", () => {
    expect(parseMarkdown("- **iron** rich foods")).toEqual([
      {
        kind: "list",
        ordered: false,
        items: [
          [
            { kind: "bold", text: "iron" },
            { kind: "text", text: " rich foods" },
          ],
        ],
      },
    ]);
  });

  it("treats a dangling list marker as plain text while it streams", () => {
    expect(parseMarkdown("Try these:\n- ")).toEqual([
      { kind: "paragraph", spans: [{ kind: "text", text: "Try these:\n- " }] },
    ]);
  });

  it("is total on pathological input", () => {
    expect(() => parseMarkdown("")).not.toThrow();
    expect(parseMarkdown("")).toEqual([]);
    expect(() => parseMarkdown("***\n\n``\n- \n1.\n**`")).not.toThrow();
    expect(() => parseMarkdown("\n".repeat(500))).not.toThrow();
  });

  it("keeps citation markers untouched for the renderer", () => {
    expect(parseMarkdown("- oatmeal [2]")).toEqual([
      { kind: "list", ordered: false, items: [[{ kind: "text", text: "oatmeal [2]" }]] },
    ]);
  });
});
