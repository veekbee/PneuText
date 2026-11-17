import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function renderApp(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

afterEach(cleanup);

describe("App", () => {
  it("shows an empty library", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json(200, { app_version: "0.1.0", schema_version: 1, created_at: "2026-01-01T00:00:00Z" }),
    );
    renderApp();
    expect(screen.getByText("Opening the library…")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "This library is empty" })).toBeTruthy();
    expect(screen.getByText(/library schema 1/)).toBeTruthy();
  });

  it("shows the server's error and recovers on retry", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(503, { detail: "The library is locked." }))
      .mockResolvedValueOnce(
        json(200, { app_version: "0.1.0", schema_version: 1, created_at: "2026-01-01T00:00:00Z" }),
      );
    renderApp();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The library is locked.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "This library is empty" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
