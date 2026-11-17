import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { type DrawnLine, layoutPage, type ShapeLineInput } from "../src/lib/pageLayout";

interface ShapeCase {
  name: string;
  measure: number;
  lines: ShapeLineInput[];
  expected: DrawnLine[];
}

// The same cases the Python implementation is held to.
const here = dirname(fileURLToPath(import.meta.url));
const { cases } = JSON.parse(
  readFileSync(join(here, "..", "..", "tests", "fixtures", "shape_cases.json"), "utf-8"),
) as { cases: ShapeCase[] };

describe("page layout (shared cases)", () => {
  it("has cases to check", () => {
    expect(cases.length).toBeGreaterThan(10);
  });

  it.each(cases)("$name", ({ measure, lines, expected }) => {
    expect(layoutPage(lines, measure)).toEqual(expected);
  });
});
