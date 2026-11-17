import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "../src/App";
import { mockApi, renderWithQuery, setUrl, VERSION } from "./helpers";

const LIBRARY = { app_version: "0.1.0", schema_version: 2, created_at: "2026-01-01T00:00:00Z" };

afterEach(cleanup);

describe("Library home", () => {
  it("shows an empty library and offers to import", async () => {
    mockApi({
      "GET /api/library": () => ({ body: LIBRARY }),
      "GET /api/versions": () => ({ body: [] }),
    });
    setUrl("/");
    renderWithQuery(<App />);
    expect(screen.getByText("Opening the library…")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "This library is empty" })).toBeTruthy();
    expect(await screen.findByText(/library schema 2/)).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "Import a corpus" }));
    expect(await screen.findByRole("heading", { name: "Import a corpus" })).toBeTruthy();
    expect(window.location.pathname).toBe("/import");
  });

  it("lists imported texts, linking each to its first page", async () => {
    mockApi({
      "GET /api/library": () => ({ body: LIBRARY }),
      "GET /api/versions": () => ({ body: [VERSION] }),
    });
    setUrl("/");
    renderWithQuery(<App />);
    const link = await screen.findByRole("link", { name: "The Fixture Book" });
    expect(link.getAttribute("href")).toBe("/v/1/p/7");
    expect(screen.getByText(/Nobody · First import · 3 pages, 7–9/)).toBeTruthy();
  });

  it("shows the server's error and recovers on retry", async () => {
    let calls = 0;
    mockApi({
      "GET /api/library": () => ({ body: LIBRARY }),
      "GET /api/versions": () =>
        calls++ === 0
          ? { status: 503, body: { detail: "The library is locked." } }
          : { body: [] },
    });
    setUrl("/");
    renderWithQuery(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The library is locked.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "This library is empty" })).toBeTruthy();
  });

  it("explains an address that leads nowhere", () => {
    mockApi({});
    setUrl("/somewhere/else");
    renderWithQuery(<App />);
    expect(screen.getByRole("alert").textContent).toContain("There is nothing at this address.");
  });
});
