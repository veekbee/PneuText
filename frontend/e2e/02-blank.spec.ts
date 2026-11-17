import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");
const PAGES = [7, 8, 9, 10, 11, 12];

/** Every line of running text in the fixture book. */
function bookLines(): string[] {
  return readdirSync(BOOK)
    .filter((name) => name.includes("_corp_"))
    .flatMap((name) => readFileSync(join(BOOK, name), "utf-8").split("\n"))
    .map((line) => line.trim())
    .filter((line) => line !== "" && !line.startsWith("<<"));
}

async function importBook(page: Page): Promise<number> {
  const response = await page.request.post("/api/imports/corpus", {
    data: {
      folder: BOOK,
      work_code: "fx",
      title: "The Fixture Book",
      author: "Nobody",
      allow_duplicate: true,
    },
  });
  expect(response.status()).toBe(201);
  return ((await response.json()) as { version_id: number }).version_id;
}

interface Row {
  id: string;
  top: number;
  height: number;
  left: number;
  right: number;
  full: boolean;
}

/** Each text row's box, and the left and right edge of what is drawn in it. */
async function rows(page: Page): Promise<Row[]> {
  return page.locator(".page-body .line").evaluateAll((elements) =>
    elements.map((row) => {
      const box = row.getBoundingClientRect();
      const bar = row.querySelector(".bar");
      let ink: DOMRect;
      if (bar) ink = bar.getBoundingClientRect();
      else {
        const range = document.createRange();
        range.selectNodeContents(row);
        ink = range.getBoundingClientRect();
      }
      return {
        id: row.id,
        top: box.top,
        height: box.height,
        left: ink.left - box.left,
        right: ink.right - box.left,
        full: row.classList.contains("full"),
      };
    }),
  );
}

test("blank mode and text mode align line for line", async ({ page }) => {
  const version = await importBook(page);
  for (const number of PAGES) {
    await page.goto(`/v/${version}/p/${number}`);
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();
    const sheet = page.getByRole("article", { name: `Page ${number}` });
    await expect(sheet).toHaveAttribute("data-mode", "text");
    const textRows = await rows(page);
    const textSheet = await sheet.boundingBox();
    const textFurniture = await page.locator(".furniture").evaluateAll((elements) =>
      elements.map((element) => {
        const box = element.getBoundingClientRect();
        return [element.className, box.top, box.height];
      }),
    );

    await page.getByRole("button", { name: "Blank" }).click();
    await expect(sheet).toHaveAttribute("data-mode", "blank");
    const blankRows = await rows(page);

    // Switching modes moves nothing: same sheet, same rows, same furniture.
    expect(await sheet.boundingBox()).toEqual(textSheet);
    expect(
      await page.locator(".furniture").evaluateAll((elements) =>
        elements.map((element) => {
          const box = element.getBoundingClientRect();
          return [element.className, box.top, box.height];
        }),
      ),
    ).toEqual(textFurniture);
    expect(blankRows.map((row) => row.id)).toEqual(textRows.map((row) => row.id));
    expect(blankRows.length).toBeGreaterThan(5);
    for (const [index, blank] of blankRows.entries()) {
      const text = textRows[index] as Row;
      expect(blank.top).toBeCloseTo(text.top, 1);
      expect(blank.height).toBeCloseTo(text.height, 1);
      // Bars begin where the words begin (so indents match)...
      expect(Math.abs(blank.left - text.left)).toBeLessThan(1.5);
      // ...and a full line's bar ends where its justified words end.
      if (blank.full) expect(Math.abs(blank.right - text.right)).toBeLessThan(1.5);
      // A paragraph's last line is set to the width its length calls for. Words can be
      // spread to fill it but a lone word cannot, so allow a little slack.
      else {
        const off = Math.abs(blank.right - text.right);
        expect(off, `page ${number} ${blank.id}: bar ${blank.right}, text ${text.right}`).toBeLessThan(
          blank.right * 0.03 + 2,
        );
      }
    }
  }
});

test("blank mode never receives or shows corpus text", async ({ page }) => {
  const version = await importBook(page);
  const lines = bookLines();
  expect(lines.length).toBe(69);

  // Start in blank mode, as a returning reader would.
  await page.addInitScript(() =>
    window.localStorage.setItem("pneutext.prefs", JSON.stringify({ mode: "blank" })),
  );
  const bodies: { url: string; body: string }[] = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (url.includes("/api/")) bodies.push({ url, body: await response.text() });
  });

  await page.goto(`/v/${version}/p/${PAGES[0]}`);
  for (const number of PAGES) {
    const sheet = page.getByRole("article", { name: `Page ${number}` });
    await expect(sheet).toHaveAttribute("data-mode", "blank");
    await expect(sheet.locator(".bar").first()).toBeVisible();
    expect((await sheet.locator(".page-body").innerText()).trim()).toBe("");
    if (number !== PAGES[PAGES.length - 1]) await page.keyboard.press("ArrowRight");
  }
  // Chapter navigation and a direct line address stay within the shape projection too.
  await page.getByRole("link", { name: /^I\s*p\. 7$/ }).click();
  await expect(page.getByRole("article", { name: "Page 7" })).toBeVisible();
  await page.goto(`/v/${version}/p/11#l2`);
  await expect(page.locator("#l2")).toHaveClass(/is-target/);

  const shapeRequests = bodies.filter(({ url }) => url.endsWith("/shape"));
  expect(shapeRequests.length).toBeGreaterThanOrEqual(PAGES.length);
  expect(bodies.filter(({ url }) => url.endsWith("/text"))).toEqual([]);
  for (const { url, body } of bodies) {
    for (const line of lines) {
      expect(body.includes(line), `${url} contains a line of the corpus`).toBe(false);
      // Not even a short run of words from a line.
      const run = line.split(" ").slice(0, 3).join(" ");
      expect(body.includes(run), `${url} contains words of the corpus`).toBe(false);
    }
  }
  // Nothing on screen either: the document holds no line of the book.
  const visible = await page.locator("body").innerText();
  for (const line of lines) expect(visible.includes(line)).toBe(false);
});
