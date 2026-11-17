import { describe, expect, it } from "vitest";

import { isVisible } from "../src/lib/filters";

const note = { type_id: 2, level: 1, status: "draft" };

describe("isVisible", () => {
  it("shows everything to a reader who has read the book", () => {
    expect(isVisible(note, { level: "all", hiddenTypes: [] })).toBe(true);
    expect(isVisible({ ...note, level: 2 }, { level: "all", hiddenTypes: [] })).toBe(true);
  });

  it("hides level 2 notes on a first reading", () => {
    expect(isVisible({ ...note, level: 2 }, { level: "first", hiddenTypes: [] })).toBe(false);
    expect(isVisible(note, { level: "first", hiddenTypes: [] })).toBe(true);
  });

  it("hides a note whose type is switched off", () => {
    expect(isVisible(note, { level: "all", hiddenTypes: [2] })).toBe(false);
    expect(isVisible(note, { level: "all", hiddenTypes: [3] })).toBe(true);
  });

  it("applies a status filter, but not to something whose status is unknown", () => {
    expect(isVisible(note, { level: "all", hiddenTypes: [], status: "ready" })).toBe(false);
    expect(isVisible(note, { level: "all", hiddenTypes: [], status: "draft" })).toBe(true);
    expect(isVisible({ type_id: 2, level: 1 }, { level: "all", hiddenTypes: [], status: "ready" })).toBe(
      true,
    );
  });
});
