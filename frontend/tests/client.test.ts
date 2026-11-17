import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../src/api/client";

function respond(status: number, body: unknown): void {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

describe("api client", () => {
  it("returns the library description", async () => {
    const library = { app_version: "0.1.0", schema_version: 1, created_at: "2026-01-01T00:00:00Z" };
    respond(200, library);
    await expect(api.getLibrary()).resolves.toEqual(library);
    expect(fetch).toHaveBeenCalledWith("/api/library", undefined);
  });

  it("surfaces the server's own explanation on an error", async () => {
    respond(503, { detail: "The library is locked." });
    const error = await api.getLibrary().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).message).toBe("The library is locked.");
  });

  it("falls back to a plain message when the error has no detail", async () => {
    respond(500, ["unexpected"]);
    await expect(api.getLibrary()).rejects.toThrow("The server answered with an error (500).");
  });

  it("explains an unreachable server in plain language", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.getLibrary()).rejects.toThrow("PneuText's server is not responding");
  });
});
