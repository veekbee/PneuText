import { describe, expect, it } from "vitest";

import { pagePath, parseRoute } from "../src/lib/route";

describe("routes", () => {
  it("parses the home and import addresses", () => {
    expect(parseRoute("/")).toEqual({ name: "home" });
    expect(parseRoute("/import")).toEqual({ name: "import" });
  });

  it("parses a page address", () => {
    expect(parseRoute("/v/3/p/45")).toEqual({ name: "page", versionId: 3, page: 45, line: null });
  });

  it("parses a line address", () => {
    expect(parseRoute("/v/3/p/45", "#l12")).toEqual({
      name: "page",
      versionId: 3,
      page: 45,
      line: 12,
    });
  });

  it("ignores a hash that is not a line", () => {
    expect(parseRoute("/v/3/p/45", "#elsewhere")).toMatchObject({ page: 45, line: null });
  });

  it("rejects anything else", () => {
    for (const path of ["/v/3", "/v/x/p/1", "/v/3/p/1/extra", "/nope"]) {
      expect(parseRoute(path)).toEqual({ name: "not-found" });
    }
  });

  it("formats addresses that parse back to the same place", () => {
    expect(pagePath(3, 45)).toBe("/v/3/p/45");
    expect(pagePath(3, 45, 12)).toBe("/v/3/p/45#l12");
    expect(parseRoute("/v/3/p/45", "#l12")).toMatchObject({ versionId: 3, page: 45, line: 12 });
  });
});
