import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import backend from "./fixtures/backend-enums.json";
import * as copy from "../copy";

const EXPORTED: unknown[] = Object.values(copy);
const RENDERED: string[] = [
  ...EXPORTED.flatMap((v) =>
    typeof v === "string" ? [v] : Array.isArray(v) ? v.filter((x) => typeof x === "string") : [],
  ),
  ...Object.values(copy.INTENT_LABELS),
  copy.overrideBody("iron", 8, 11, "mg"),
  copy.UNAVAILABLE("OPENROUTER_API_KEY is not set."),
];

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      return entry === "ui" || entry === "__tests__" ? [] : tsxFiles(full);
    }
    return full.endsWith(".tsx") && !full.endsWith(".test.tsx") ? [full] : [];
  });
}

describe("product copy", () => {
  it("is reviewed as one snapshot", () => {
    expect(copy).toMatchSnapshot();
  });

  it("has no exclamation marks and never reads as a missing child", () => {
    for (const text of RENDERED) {
      expect(text.trim().length).toBeGreaterThan(0);
      expect(text).not.toContain("!");
      expect(text.toLowerCase()).not.toContain("missing child");
    }
    for (const key of Object.keys(copy)) {
      expect(key.toLowerCase()).not.toContain("missing_child_hint");
    }
  });

  it("disclaimer fallback matches the backend verbatim", () => {
    expect(copy.DISCLAIMER_FALLBACK).toBe(backend.disclaimer);
  });

  it("override body names both values", () => {
    expect(copy.overrideBody("iron", 8, 11, "mg")).toBe(
      "We're using 8 mg instead of the usual 11 mg for iron, just as your doctor asked",
    );
    expect(copy.overrideBody("calories", 650, 743, "kcal")).toContain("650 kcal");
  });

  it("no long JSX text literal lives outside copy.ts", () => {
    const roots = ["src/components", "src/app"].map((p) => path.resolve(process.cwd(), p));
    const offenders: string[] = [];
    for (const root of roots) {
      let files: string[] = [];
      try {
        files = tsxFiles(root);
      } catch {
        continue;
      }
      for (const file of files) {
        const source = readFileSync(file, "utf8");
        // Prose between tags, e.g. `<p>Some long sentence here</p>`. Only letters,
        // spaces and sentence punctuation count, so code between `=>` and `<` is ignored.
        for (const match of source.matchAll(/>\s*([^<>{}\n]{25,})\s*</g)) {
          const text = match[1].trim();
          if (/^[A-Za-z][A-Za-z ,.'’—-]{24,}$/.test(text) && text.includes(" ")) {
            offenders.push(`${path.relative(process.cwd(), file)}: "${text}"`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
