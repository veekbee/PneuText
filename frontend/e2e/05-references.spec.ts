import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

async function importBook(page: Page): Promise<number> {
  const response = await page.request.post("/api/imports/corpus", {
    data: { folder: BOOK, work_code: "fx", title: "The Fixture Book", allow_duplicate: true },
  });
  return ((await response.json()) as { version_id: number }).version_id;
}

/** Select a phrase on one print line, as a reader would, and release the mouse. */
async function select(page: Page, line: number, phrase: string): Promise<void> {
  await page.evaluate(
    ([lineNo, words]) => {
      const row = document.getElementById(`l${lineNo}`);
      if (!row) throw new Error(`no line ${lineNo}`);
      const index = (row.textContent ?? "").indexOf(words);
      if (index === -1) throw new Error("phrase not on that line");
      const point = (offset: number): [Node, number] => {
        let remaining = offset;
        const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          const length = node.textContent?.length ?? 0;
          if (remaining <= length) return [node, remaining];
          remaining -= length;
        }
        throw new Error("past the line");
      };
      const range = document.createRange();
      range.setStart(...point(index));
      range.setEnd(...point(index + words.length));
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    },
    [line, phrase] as const,
  );
}

test("insert a reference and follow it both ways; it survives an edit", async ({ page }) => {
  const version = await importBook(page);
  await page.goto(`/v/${version}/p/8`);
  await expect(page.locator("#l3")).toContainText("single heron");

  // Write a note on page 8 and insert a reference to a line of page 10 with the picker.
  await select(page, 3, "single heron");
  const popover = page.getByRole("dialog", { name: "Selection" });
  await popover.getByRole("button", { name: "Note", exact: true }).click();
  await popover.getByRole("button", { name: "Comment", exact: true }).click();
  const form = page.getByRole("form", { name: "Edit note" });
  await form.getByRole("textbox", { name: "Note", exact: true }).fill("The bird returns: ");
  await form.getByLabel("Page or lines").fill("10.2");
  await form.getByRole("button", { name: "Insert" }).click();
  await expect(form.getByRole("textbox", { name: "Note", exact: true })).toHaveValue("The bird returns: {{fx:10.2}}");
  // The live preview already shows it as a resolved page citation.
  await expect(form.getByRole("region", { name: "Preview" }).getByRole("link")).toHaveText("p. 10.2");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toHaveCount(0);

  // Forwards: the reference shows the page and opens the target, with its line marked.
  await page.locator(".note-card").getByRole("link", { name: "p. 10.2" }).click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/10#l2$`));
  await expect(page.getByRole("article", { name: "Page 10" }).locator("#l2")).toHaveClass(/is-target/);

  // Backwards: the target page lists the note as a backlink, which leads home again.
  const referredFrom = page.getByRole("region", { name: "Referred to from" });
  await expect(referredFrom.getByRole("listitem")).toHaveText(["Comment, p. 8.3 cites p. 10.2"]);
  await referredFrom.getByRole("link", { name: "Comment, p. 8.3" }).click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/8#l3$`));
  await expect(page.locator(".note-card")).toContainText("The bird returns:");

  // Edit the note without touching the reference: the backlink survives.
  await page.locator(".note-card").getByRole("button", { name: "Edit", exact: true }).click();
  await form.getByRole("textbox", { name: "Note", exact: true }).fill("The bird returns, patiently: {{fx:10.2}}");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toHaveCount(0);
  await page.goto(`/v/${version}/p/10`);
  await expect(referredFrom.getByRole("listitem")).toHaveText(["Comment, p. 8.3 cites p. 10.2"]);

  // Point it somewhere else: the backlink moves with it, and a bad reference shows as broken.
  await page.goto(`/v/${version}/p/8`);
  await page.locator(".note-card").getByRole("button", { name: "Edit", exact: true }).click();
  await form.getByRole("textbox", { name: "Note", exact: true }).fill("See {{fx:12}} and {{fx:99}}.");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toHaveCount(0);
  await expect(page.locator(".note-card .broken")).toHaveText("{{fx:99}}");
  await page.goto(`/v/${version}/p/10`);
  await expect(page.getByRole("region", { name: "Referred to from" })).toHaveCount(0);
  await page.goto(`/v/${version}/p/12`);
  await expect(referredFrom.getByRole("listitem")).toHaveText(["Comment, p. 8.3 cites p. 12"]);
});

test("search finds the text and notes, and a passage can be linked to another", async ({ page }) => {
  const version = await importBook(page);
  await page.request.post(`/api/versions/${version}/imports/commentary`, {
    data: { folder: BOOK, page_ref_commands: ["pref"] },
  });
  await page.goto(`/v/${version}/p/7`);
  await expect(page.locator("#l3")).toBeVisible();

  // Search: the text and the notes are listed separately.
  await page.keyboard.press("/");
  await page.keyboard.type("senora");
  const results = page.getByRole("region", { name: "Search results" });
  await expect(results.getByRole("region", { name: "In the text" }).getByRole("button")).toHaveText([
    /8\.10.*señora/,
  ]);
  await expect(results.getByRole("region", { name: "In notes" }).getByRole("button")).toHaveText([
    /Spanish, p\. 8.*señora/,
  ]);
  await results.getByRole("region", { name: "In the text" }).getByRole("button").click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/8#l10$`));

  // The imported gloss, figure and to-do render as such.
  await expect(page.locator(".note-card .gloss")).toHaveText("señora (madam, lady)");
  await page.goto(`/v/${version}/p/7`);
  await expect(page.locator(".note-card .note-figure img")).toBeVisible();
  const loaded = await page
    .locator(".note-card .note-figure img")
    .evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0);
  expect(loaded).toBe(true);
  await expect(page.locator(".note-card .todo").first()).toContainText("To do");

  // Link a passage on page 7 to one on page 8 through the tray.
  await select(page, 9, "biscuit tin");
  await page.getByRole("dialog", { name: "Selection" }).getByRole("button", { name: "Link", exact: true }).click();
  await expect(page.getByRole("status", { name: "Link in progress" })).toContainText("p. 7.9");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("article", { name: "Page 8" })).toBeVisible();
  await expect(page.getByRole("status", { name: "Link in progress" })).toBeVisible();
  await select(page, 9, "eels");
  await page.getByRole("dialog", { name: "Selection" }).getByRole("button", { name: "Link here" }).click();
  await expect(page.getByRole("status", { name: "Link in progress" })).toHaveCount(0);

  const linked = page.getByRole("region", { name: "Linked passages" });
  await expect(linked.getByRole("listitem")).toContainText(["p. 8.9 ↔ p. 7.9"]);
  await linked.getByRole("link", { name: "p. 7.9" }).click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/7#l9$`));
  await expect(linked.getByRole("listitem")).toContainText(["p. 7.9 ↔ p. 8.9"]);

  // In blank mode the text is not searched, and no corpus text arrives.
  await page.getByRole("button", { name: "Blank" }).click();
  const responses: string[] = [];
  page.on("response", async (response) => {
    if (response.url().includes("/search")) responses.push(await response.text());
  });
  await page.getByRole("searchbox", { name: "Search" }).fill("heron");
  await expect(results).toContainText("The text itself is not searched in blank mode.");
  await expect(results.getByRole("region", { name: "In the text" })).toHaveCount(0);
  expect(responses.length).toBeGreaterThan(0);
  for (const body of responses) expect(body).not.toContain("stood in them");
});
