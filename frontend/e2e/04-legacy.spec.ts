import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

test("import the old commentary: dry run, report, import, and import again", async ({ page }) => {
  const created = await page.request.post("/api/imports/corpus", {
    data: { folder: BOOK, work_code: "fx", title: "The Fixture Book", allow_duplicate: true },
  });
  const version = ((await created.json()) as { version_id: number }).version_id;

  await page.goto(`/v/${version}/import-commentary`);
  await page.getByLabel("Folder of commentary files").fill(BOOK);
  await page.getByText("More options").click();
  await page.getByLabel(/LaTeX commands that cite a page/).fill("pref");
  await page.getByRole("button", { name: "Check the folder" }).click();

  // The dry run reports every planted problem, grouped, and has written nothing.
  const report = page.getByRole("region", { name: "What was found" });
  await expect(report).toContainText("Notes13");
  await expect(report).toContainText("Flagged3");
  await expect(report).toContainText("Entity mentions16");
  await expect(report.getByRole("region", { name: "Unclosed or malformed tags" })).toContainText(
    "{m_p9_white} is never closed",
  );
  await expect(report.getByRole("region", { name: "Spans without a note" })).toContainText(
    "{c_p8_marsh}",
  );
  await expect(report.getByRole("region", { name: "Notes without a span" })).toContainText(
    "{c_p8_barrow}",
  );
  await expect(report.getByRole("region", { name: "Ids naming another page" })).toContainText(
    "{c_p7_sheet} names page 7",
  );
  await expect(report.getByRole("region", { name: "Repairs" })).toContainText(
    "|times| was read as the category time",
  );
  const before = await page.request.get(`/api/versions/${version}/pages/7/notes`);
  expect(await before.json()).toEqual([]);

  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Imported.");
  await page.getByRole("link", { name: "Open page 7" }).click();

  // Page 7: chapter matter, a remark, and five notes on nested and overlapping spans.
  await expect(page.locator(".note-card")).toHaveCount(8);
  await expect(page.locator(".note-card .note-type")).toHaveText([
    "Chapter title",
    "Chapter summary",
    "Comment",
    "Historical",
    "Comment",
    "Definition",
    "Literary",
    "Meditation",
  ]);
  await expect(page.locator("#l9 .hl")).toHaveText(["kept his ledgers in a ", "biscuit tin", ". He told her"]);
  await expect(page.locator("#l4 .hl")).toHaveText(["October, 1871"]);
  await expect(page.locator(".note-card").nth(4)).toContainText("Have read");
  await expect(page.locator(".note-card").nth(4).locator("strong")).toHaveText("Watch");

  // Importing again replaces the imported notes instead of doubling them.
  await page.goto(`/v/${version}/import-commentary`);
  await page.getByLabel("Folder of commentary files").fill(BOOK);
  await page.getByRole("button", { name: "Check the folder" }).click();
  await expect(page.getByRole("alert")).toContainText("replaces 16 notes and 16 mentions");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Imported.");
  await page.goto(`/v/${version}/p/7`);
  await expect(page.locator(".note-card")).toHaveCount(8);
});
