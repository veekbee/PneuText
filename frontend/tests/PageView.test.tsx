import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PageView } from "../src/page/PageView";
import { line, shapeLine } from "./helpers";

afterEach(cleanup);

function renderPage(targetLine: number | null = null) {
  const lines = [
    line("IV", { kind: "chapter_number", line_no: null }),
    line("", { kind: "ornament", line_no: null }),
    line("", { kind: "rule", line_no: null }),
    line("a synopsis line", { kind: "synopsis", line_no: 1, starts_paragraph: true }),
    line("a first line that is full", { line_no: 2, starts_paragraph: true, segment_id: 9 }),
    line("a short last line", { line_no: 3, ends_paragraph: true, start_offset: 26 }),
    line("carried over and <b>not markup</b>", { line_no: 4, ends_paragraph: true }),
    line("fifth", { line_no: 5, starts_paragraph: true, ends_paragraph: true }),
  ];
  return render(
    <PageView mode="text" page={45} measure={30} lines={lines} targetLine={targetLine} />,
  );
}

describe("PageView", () => {
  it("draws one row per print line, in order, with its words", () => {
    const { container } = renderPage();
    const rows = [...container.querySelectorAll(".line")].map((row) => row.textContent);
    expect(rows).toEqual([
      "a synopsis line",
      "a first line that is full",
      "a short last line",
      "carried over and <b>not markup</b>",
      "fifth",
    ]);
  });

  it("indents a paragraph's first line and justifies all but its last", () => {
    const { container } = renderPage();
    const first = container.querySelector("#l2");
    const last = container.querySelector("#l3");
    expect(first?.classList.contains("indent")).toBe(true);
    expect(first?.classList.contains("full")).toBe(true);
    expect(last?.classList.contains("indent")).toBe(false);
    expect(last?.classList.contains("last")).toBe(true);
  });

  it("does not indent a paragraph continued from the previous page", () => {
    const { container } = renderPage();
    expect(container.querySelector("#l4")?.classList.contains("indent")).toBe(false);
  });

  it("draws furniture as placeholders, keeping only the chapter number's text", () => {
    const { container } = renderPage();
    expect(container.querySelector(".chapter-number")?.textContent).toBe("IV");
    expect(container.querySelector(".ornament")?.textContent).toBe("");
    expect(container.querySelector(".rule")?.textContent).toBe("");
    expect(container.querySelectorAll(".furniture[id]").length).toBe(0);
  });

  it("gives each text line an address and its place in the text", () => {
    const { container } = renderPage();
    const row = container.querySelector("#l3") as HTMLElement;
    expect(row.dataset.lineNo).toBe("3");
    expect(row.dataset.startOffset).toBe("26");
    expect((container.querySelector("#l2") as HTMLElement).dataset.segmentId).toBe("9");
  });

  it("numbers every fifth line in the gutter", () => {
    const { container } = renderPage();
    const marked = [...container.querySelectorAll("[data-gutter]")].map((row) => row.id);
    expect(marked).toEqual(["l5"]);
  });

  it("renders corpus text as text, never as markup", () => {
    const { container } = renderPage();
    expect(container.querySelector("b")).toBeNull();
  });

  it("marks the target line", () => {
    const { container } = renderPage(3);
    const targets = [...container.querySelectorAll(".is-target")].map((row) => row.id);
    expect(targets).toEqual(["l3"]);
  });

  it("carries the measure and the page number", () => {
    const { container, getByLabelText } = renderPage();
    const page = getByLabelText("Page 45");
    expect(page.style.getPropertyValue("--measure")).toBe("30");
    expect(container.querySelector(".page-number")?.textContent).toBe("45");
  });
});

function renderBlank(targetLine: number | null = null) {
  const lines = [
    shapeLine(0, { kind: "chapter_number", line_no: null }),
    shapeLine(0, { kind: "rule", line_no: null }),
    shapeLine(40, { line_no: 1, starts_paragraph: true }),
    shapeLine(25, {
      line_no: 2,
      ends_paragraph: true,
      highlights: [
        { annotation_id: 7, type_id: 2, start: 0, end: 10 },
        { annotation_id: 8, type_id: 3, start: 5, end: 25 },
      ],
    }),
  ];
  return render(<PageView mode="blank" page={45} measure={50} lines={lines} targetLine={targetLine} />);
}

describe("PageView in blank mode", () => {
  it("draws the same rows with the same addresses, and no words at all", () => {
    const { container } = renderBlank();
    const rows = [...container.querySelectorAll(".line")];
    expect(rows.map((row) => row.id)).toEqual(["l1", "l2"]);
    expect(container.querySelector(".page-body")?.textContent).toBe("");
    expect(container.querySelector("[data-segment-id]")).toBeNull();
  });

  it("places each bar by the page-shape rules", () => {
    const { container } = renderBlank();
    const [first, last] = [...container.querySelectorAll<HTMLElement>(".bar")];
    expect([first?.style.left, first?.style.width]).toEqual(["6%", "94%"]);
    expect([last?.style.left, last?.style.width]).toEqual(["0%", "50%"]);
  });

  it("stacks overlapping highlights as bands on the bar", () => {
    const { container } = renderBlank();
    const marks = [...container.querySelectorAll<HTMLElement>(".bar-highlight")];
    expect(marks.map((mark) => mark.dataset.annotationId)).toEqual(["7", "8"]);
    expect(marks.map((mark) => mark.style.getPropertyValue("--band"))).toEqual(["0", "1"]);
    expect(marks.map((mark) => mark.style.getPropertyValue("--bands"))).toEqual(["2", "2"]);
    expect(marks.map((mark) => [mark.style.left, mark.style.width])).toEqual([
      ["0%", "20%"],
      ["10%", "40%"],
    ]);
  });

  it("draws the chapter number as a placeholder, not a numeral", () => {
    const { container } = renderBlank();
    expect(container.querySelector(".chapter-number")?.textContent).toBe("");
    expect(container.querySelector(".chapter-number .placeholder")).not.toBeNull();
  });

  it("marks the target line and says which mode it is in", () => {
    const { container, getByLabelText } = renderBlank(2);
    expect([...container.querySelectorAll(".is-target")].map((row) => row.id)).toEqual(["l2"]);
    expect(getByLabelText("Page 45").dataset.mode).toBe("blank");
  });
});
