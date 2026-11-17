import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

test("import the fixture book and turn its pages", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "This library is empty" })).toBeVisible();

  await page.getByRole("link", { name: "Import a corpus" }).click();
  await page.getByLabel("Folder of page files").fill(BOOK);
  await page.getByLabel("Title").fill("The Fixture Book");
  await page.getByLabel("Author").fill("Nobody");
  await page.getByLabel("Short code").fill("fx");
  await page.getByRole("button", { name: "Check the folder" }).click();

  const summary = page.getByRole("region", { name: "What was found" });
  await expect(summary).toContainText("Pages6 (7–12)");
  await expect(summary).toContainText("Chapters2");
  await expect(summary).toContainText("Warnings0");
  await page.getByRole("button", { name: "Import", exact: true }).click();

  // The book opens at its first page: a chapter opening.
  await expect(page).toHaveURL(/\/v\/1\/p\/7$/);
  const sheet = page.getByRole("article", { name: "Page 7" });
  await expect(sheet.locator(".chapter-number")).toHaveText("I");
  await expect(sheet.locator("#l3")).toHaveText("The ferry came into Low Harbor on the last tide of");

  // Pages turn with the link and with the keyboard, and the address follows.
  await page.getByRole("link", { name: "Next ›" }).click();
  await expect(page.getByRole("article", { name: "Page 8" })).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/\/v\/1\/p\/9$/);
  await page.keyboard.press("ArrowLeft");
  await expect(page).toHaveURL(/\/v\/1\/p\/8$/);

  // Chapter navigation and go-to-page.
  await page.getByRole("link", { name: /^II\s*p\. 10$/ }).click();
  await expect(page.getByRole("article", { name: "Page 10" }).locator(".chapter-number")).toHaveText("II");
  await page.keyboard.press("g");
  await page.keyboard.type("12");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article", { name: "Page 12" })).toBeVisible();
  await expect(page.getByText("Next ›")).toHaveAttribute("aria-disabled", "true");

  // A page address survives a reload, and a line address marks its line.
  await page.goto("/v/1/p/11#l2");
  await expect(page.getByRole("article", { name: "Page 11" }).locator("#l2")).toHaveClass(/is-target/);

  // Browser history walks back through the pages.
  await page.goBack();
  await expect(page).toHaveURL(/\/v\/1\/p\/12$/);
});

test("a full print line is stretched to the measure and a last line is not", async ({ page }) => {
  await page.goto("/v/1/p/7");
  const body = page.locator(".page-body");
  await expect(body).toBeVisible();
  const width = (await body.boundingBox())?.width ?? 0;

  // Measure the ink of each line: the box around its text, not around its row.
  const inkWidths = await page.locator(".line.paragraph").evaluateAll((rows) =>
    rows.map((row) => {
      const range = document.createRange();
      range.selectNodeContents(row);
      const box = range.getBoundingClientRect();
      return { full: row.classList.contains("full"), indent: row.classList.contains("indent"),
        left: box.left - row.getBoundingClientRect().left, right: box.right - row.getBoundingClientRect().left };
    }),
  );
  expect(inkWidths.length).toBeGreaterThan(8);
  for (const line of inkWidths) {
    if (line.full) expect(Math.abs(line.right - width)).toBeLessThan(2);
    else expect(line.right).toBeLessThan(width - 2);
    if (line.indent) expect(line.left).toBeGreaterThan(5);
  }
});
