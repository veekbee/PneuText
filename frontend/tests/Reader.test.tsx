import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "../src/App";
import {
  forgetPrefs,
  mockApi,
  pageOf,
  renderWithQuery,
  setUrl,
  shapeOf,
  TYPES,
  VERSION,
} from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

function mockBook() {
  return mockApi({
    "GET /api/versions/1": () => ({ body: VERSION }),
    "GET /api/note-types": () => ({ body: TYPES }),
    ...Object.fromEntries(
      [7, 8, 9].map((page) => [`GET /api/versions/1/pages/${page}/notes`, () => ({ body: [] })]),
    ),
    "GET /api/versions/1/pages/7/text": () => ({ body: pageOf(7, "seventh page words") }),
    "GET /api/versions/1/pages/8/text": () => ({ body: pageOf(8, "eighth page words") }),
    "GET /api/versions/1/pages/9/text": () => ({ body: pageOf(9, "ninth page words") }),
    "GET /api/versions/1/pages/7/shape": () => ({ body: shapeOf(7) }),
    "GET /api/versions/1/pages/8/shape": () => ({ body: shapeOf(8) }),
    "GET /api/versions/1/pages/99/text": () => ({
      status: 404,
      body: { detail: "This text has no page 99." },
    }),
    "GET /api/versions/5": () => ({
      status: 404,
      body: { detail: "There is no text with id 5 in this library." },
    }),
  });
}

describe("Reader", () => {
  it("shows the page named by the address, with the work's title", async () => {
    mockBook();
    setUrl("/v/1/p/8");
    renderWithQuery(<App />);
    expect(await screen.findByText("eighth page words")).toBeTruthy();
    expect(screen.getByText("The Fixture Book")).toBeTruthy();
    expect(screen.getByLabelText("Page 8")).toBeTruthy();
  });

  it("turns pages with the next and previous links", async () => {
    mockBook();
    setUrl("/v/1/p/7");
    renderWithQuery(<App />);
    await screen.findByText("seventh page words");
    expect(screen.getByText("‹ Previous").getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(screen.getByText("Next ›"));
    expect(await screen.findByText("eighth page words")).toBeTruthy();
    expect(window.location.pathname).toBe("/v/1/p/8");
    fireEvent.click(screen.getByText("‹ Previous"));
    expect(await screen.findByText("seventh page words")).toBeTruthy();
  });

  it("turns pages with the arrow keys, and stops at the ends", async () => {
    mockBook();
    setUrl("/v/1/p/8");
    renderWithQuery(<App />);
    await screen.findByText("eighth page words");
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByText("ninth page words")).toBeTruthy();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(window.location.pathname).toBe("/v/1/p/9");
  });

  it("goes to a typed page number", async () => {
    mockBook();
    setUrl("/v/1/p/7");
    renderWithQuery(<App />);
    await screen.findByText("seventh page words");
    const input = screen.getByLabelText("Go to page");
    fireEvent.change(input, { target: { value: "9" } });
    fireEvent.submit(input);
    expect(await screen.findByText("ninth page words")).toBeTruthy();
  });

  it("does not turn the page while typing in a field", async () => {
    mockBook();
    setUrl("/v/1/p/8");
    renderWithQuery(<App />);
    await screen.findByText("eighth page words");
    fireEvent.keyDown(screen.getByLabelText("Go to page"), { key: "ArrowRight" });
    expect(window.location.pathname).toBe("/v/1/p/8");
  });

  it("lists chapters, marks the current one, and jumps to a chapter's first page", async () => {
    mockBook();
    setUrl("/v/1/p/7");
    renderWithQuery(<App />);
    await screen.findByText("seventh page words");
    const chapterOne = screen.getByRole("link", { name: /^I\s*p\. 7$/ });
    const chapterTwo = screen.getByRole("link", { name: /^II\s*p\. 9$/ });
    expect(chapterOne.getAttribute("aria-current")).toBe("true");
    fireEvent.click(chapterTwo);
    expect(await screen.findByText("ninth page words")).toBeTruthy();
    await waitFor(() => expect(chapterTwo.getAttribute("aria-current")).toBe("true"));
  });

  it("marks the line named in the address", async () => {
    mockBook();
    setUrl("/v/1/p/7#l1");
    renderWithQuery(<App />);
    const row = await screen.findByText("seventh page words");
    expect(row.classList.contains("is-target")).toBe(true);
  });

  it("explains a page that does not exist and offers the first page", async () => {
    mockBook();
    setUrl("/v/1/p/99");
    renderWithQuery(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("This text has no page 99.");
    fireEvent.click(screen.getByText("Go to the first page"));
    expect(await screen.findByText("seventh page words")).toBeTruthy();
  });

  it("explains a text that does not exist", async () => {
    mockBook();
    setUrl("/v/5/p/1");
    renderWithQuery(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("There is no text with id 5");
  });
});

function requested(fetchMock: ReturnType<typeof mockBook>): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
}

describe("Reader in blank mode", () => {
  it("switches to blank mode with one control and shows no words", async () => {
    mockBook();
    setUrl("/v/1/p/7");
    renderWithQuery(<App />);
    await screen.findByText("seventh page words");
    fireEvent.click(screen.getByRole("button", { name: "Blank" }));
    await waitFor(() => expect(screen.getByLabelText("Page 7").dataset.mode).toBe("blank"));
    expect(screen.queryByText("seventh page words")).toBeNull();
    expect(screen.getByRole("button", { name: "Blank" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelectorAll(".bar").length).toBe(1);
  });

  it("requests only the shape projection while in blank mode", async () => {
    window.localStorage.setItem("pneutext.prefs", JSON.stringify({ mode: "blank" }));
    const fetchMock = mockBook();
    setUrl("/v/1/p/7");
    renderWithQuery(<App />);
    await waitFor(() => expect(screen.getByLabelText("Page 7").dataset.mode).toBe("blank"));
    fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByLabelText("Page 8").dataset.mode).toBe("blank"));
    const urls = requested(fetchMock);
    expect(urls).toContain("/api/versions/1/pages/8/shape");
    expect(urls.filter((url) => url.endsWith("/text"))).toEqual([]);
  });

  it("toggles with the b key and remembers the mode", async () => {
    mockBook();
    setUrl("/v/1/p/7");
    const first = renderWithQuery(<App />);
    await screen.findByText("seventh page words");
    fireEvent.keyDown(window, { key: "b" });
    await waitFor(() => expect(screen.getByLabelText("Page 7").dataset.mode).toBe("blank"));
    expect(JSON.parse(window.localStorage.getItem("pneutext.prefs") ?? "{}")).toMatchObject({
      mode: "blank",
    });
    first.unmount();
    renderWithQuery(<App />);
    await waitFor(() => expect(screen.getByLabelText("Page 7").dataset.mode).toBe("blank"));
    fireEvent.keyDown(window, { key: "b" });
    expect(await screen.findByText("seventh page words")).toBeTruthy();
  });
});
