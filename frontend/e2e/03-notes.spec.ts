import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

async function importBook(page: Page): Promise<number> {
  const response = await page.request.post("/api/imports/corpus", {
    data: { folder: BOOK, work_code: "fx", title: "The Fixture Book", allow_duplicate: true },
  });
  expect(response.status()).toBe(201);
  return ((await response.json()) as { version_id: number }).version_id;
}

/**
 * Select from the start of one phrase to the end of another, as a reader dragging the
 * mouse would, and release. Each phrase is found within its own print line.
 */
async function select(
  page: Page,
  from: { line: number; phrase: string },
  to: { line: number; phrase: string } = from,
): Promise<void> {
  await page.evaluate(
    ([start, end]) => {
      const point = (target: { line: number; phrase: string }, atEnd: boolean): [Node, number] => {
        const row = document.getElementById(`l${target.line}`);
        if (!row) throw new Error(`no line ${target.line}`);
        const index = (row.textContent ?? "").indexOf(target.phrase);
        if (index === -1) throw new Error(`phrase not on line ${target.line}`);
        let remaining = index + (atEnd ? target.phrase.length : 0);
        const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          const length = node.textContent?.length ?? 0;
          if (remaining <= length) return [node, remaining];
          remaining -= length;
        }
        throw new Error("phrase runs past the line");
      };
      const range = document.createRange();
      range.setStart(...point(start, false));
      range.setEnd(...point(end, true));
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    },
    [from, to] as const,
  );
}

async function choose(page: Page, action: "Note" | "Highlight", type: string): Promise<void> {
  const popover = page.getByRole("dialog", { name: "Selection" });
  await popover.getByRole("button", { name: action, exact: true }).click();
  await popover.getByRole("button", { name: type, exact: true }).click();
}

async function writeNote(page: Page, body: string): Promise<void> {
  const form = page.getByRole("form", { name: "Edit note" });
  await form.getByLabel("Note", { exact: true }).fill(body);
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toHaveCount(0);
}

/** The highlighted pieces of a line: their words and how many notes cover each. */
async function pieces(page: Page, line: number): Promise<[string, number][]> {
  return page.locator(`#l${line} .hl`).evaluateAll((spans) =>
    spans.map((span) => [
      span.textContent ?? "",
      ((span as HTMLElement).dataset.notes ?? "").split(" ").length,
    ]),
  );
}

test("select, annotate, reload: nested and overlapping notes of several types survive", async ({
  page,
}) => {
  const version = await importBook(page);
  await page.goto(`/v/${version}/p/7`);
  await expect(page.locator("#l9")).toContainText("kept his ledgers in a biscuit tin");

  // An outer note, a nested bare highlight, and a note that partly overlaps the first.
  await select(page, { line: 9, phrase: "kept his ledgers in a biscuit tin" });
  await choose(page, "Note", "Historical");
  await writeNote(page, "The tin *recurs*.");

  await select(page, { line: 9, phrase: "ledgers" });
  await choose(page, "Highlight", "Clarification");
  await expect(page.locator(".note-card")).toHaveCount(2);

  await select(page, { line: 9, phrase: "biscuit tin. He told her" });
  await choose(page, "Note", "Literary");
  await writeNote(page, "A sentence that **turns**.");

  const expected: [string, number][] = [
    ["kept his ", 1],
    ["ledgers", 2],
    [" in a ", 1],
    ["biscuit tin", 2],
    [". He told her", 1],
  ];
  await expect.poll(() => pieces(page, 9)).toEqual(expected);

  // A passage that crosses a print line.
  await select(page, { line: 5, phrase: "brass" }, { line: 6, phrase: "theodolite" });
  await choose(page, "Note", "Comment");
  await writeNote(page, "An instrument.");
  await expect.poll(() => pieces(page, 5)).toEqual([["brass", 1]]);
  await expect.poll(() => pieces(page, 6)).toEqual([["theodolite", 1]]);

  // Everything survives a reload, in reading order, each in its own type.
  await page.reload();
  await expect.poll(() => pieces(page, 9)).toEqual(expected);
  await expect.poll(() => pieces(page, 6)).toEqual([["theodolite", 1]]);
  await expect(page.locator(".note-card .note-type")).toHaveText([
    "Comment",
    "Historical",
    "Clarification",
    "Literary",
  ]);
  await expect(page.locator(".note-card").nth(1).locator("em")).toHaveText("recurs");
  await expect(page.locator(".note-card").nth(2)).toContainText("Highlight only.");
  await expect(page.locator(".note-card").nth(3).locator("strong")).toHaveText("turns");

  // The line still reads exactly as before: highlighting changes no text.
  await expect(page.locator("#l9")).toHaveText("kept his ledgers in a biscuit tin. He told her the");

  // Clicking a highlight brings its note into view; hovering emphasizes it.
  await page.locator("#l6 .hl").hover();
  await expect(page.locator(".note-card").first()).toHaveClass(/is-active/);
});

test("a passage can run on to the next page", async ({ page }) => {
  const version = await importBook(page);
  await page.goto(`/v/${version}/p/10`);
  await expect(page.locator("#l13")).toContainText("and then");

  await select(page, { line: 13, phrase: "and then" });
  await page.getByRole("button", { name: "Continue on next page" }).click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/11$`));
  await expect(page.getByRole("status")).toContainText("begun on page 10");
  await expect(page.getByRole("article", { name: "Page 11" })).toBeVisible();

  await select(page, { line: 1, phrase: "drawn north" });
  await choose(page, "Note", "Comment");
  await writeNote(page, "Upside down.");

  // From the top of this page to the end of the selection.
  await expect.poll(() => pieces(page, 1)).toEqual([["understood that he had drawn north", 1]]);
  await expect(page.locator(".note-card .note-place")).toHaveText("from p. 10");
  await page.goto(`/v/${version}/p/10`);
  await expect.poll(() => pieces(page, 13)).toEqual([["and then", 1]]);
  await expect(page.locator(".note-card")).toContainText("Upside down.");
});

test("blank mode shows where notes attach, read-only, without the words", async ({ page }) => {
  // The first test of this file left four notes on page 7 of the version before the last.
  const versions = (await (await page.request.get("/api/versions")).json()) as { id: number }[];
  const version = Math.max(...versions.map((item) => item.id)) - 1;
  await page.goto(`/v/${version}/p/7`);
  await page.getByRole("button", { name: "Blank" }).click();
  const sheet = page.getByRole("article", { name: "Page 7" });
  await expect(sheet).toHaveAttribute("data-mode", "blank");

  // Three notes cross line 9; the two that overlap the first sit in a second band.
  const bands = await page.locator("#l9 .bar-highlight").evaluateAll((marks) =>
    marks.map((mark) => (mark as HTMLElement).style.getPropertyValue("--band")),
  );
  expect(bands).toEqual(["0", "1", "1"]);
  expect((await sheet.locator(".page-body").innerText()).trim()).toBe("");

  await expect(page.locator(".note-card")).toHaveCount(4);
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Note on this page" })).toHaveCount(0);

  if (process.env.SHOT) {
    await page.setViewportSize({ width: 1400, height: 900 });
    await page.screenshot({ path: `${process.env.SHOT}-notes-blank.png` });
    await page.getByRole("button", { name: "Text" }).click();
    await expect(sheet).toHaveAttribute("data-mode", "text");
    await page.screenshot({ path: `${process.env.SHOT}-notes-text.png` });
  }
});
