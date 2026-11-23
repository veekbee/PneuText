import { cpSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

test("correct a page file and update the text; the note stays on its words", async ({ page }) => {
  // A private copy of the fixture pages, so that one of them can be corrected.
  const folder = mkdtempSync(join(tmpdir(), "pneutext-pages-"));
  for (const name of readdirSync(BOOK).filter((file) => file.includes("_corp_"))) {
    cpSync(join(BOOK, name), join(folder, name));
  }
  const created = await page.request.post("/api/imports/corpus", {
    data: { folder, work_code: "fx", title: "The Fixture Book", label: "To be corrected", allow_duplicate: true },
  });
  const version = ((await created.json()) as { version_id: number }).version_id;

  // Mark "heron" on page 8 through the API, as the reader would by selecting it.
  const text = (await (await page.request.get(`/api/versions/${version}/pages/8/text`)).json()) as {
    lines: { segment_id: number; start_offset: number; text: string }[];
  };
  const line = text.lines.find((candidate) => candidate.text.includes("heron"));
  if (line === undefined) throw new Error("the fixture page has no heron");
  const start = line.start_offset + line.text.indexOf("heron");
  const types = (await (await page.request.get("/api/note-types")).json()) as { id: number }[];
  const noted = await page.request.post(`/api/versions/${version}/notes`, {
    data: {
      type_id: types[0]?.id,
      body_md: "A bird worth watching.",
      span: {
        start_segment_id: line.segment_id,
        start_offset: start,
        end_segment_id: line.segment_id,
        end_offset: start + 5,
        exact: "heron",
      },
    },
  });
  expect(noted.status()).toBe(201);

  const file = join(folder, "FX_corp_p008.txt");
  writeFileSync(file, readFileSync(file, "utf8").replace("single heron", "solitary gray heron"));

  await page.goto(`/v/${version}/update-text`);
  await page.getByLabel("Folder of page files").fill(folder);
  await page.getByRole("button", { name: "Check the folder" }).click();
  const report = page.getByRole("region", { name: "What differs" });
  await expect(report).toContainText("Changes on page 8, in 1 paragraph.");
  await expect(report).toContainText("1 marked passage will be shifted");
  await page.getByRole("button", { name: "Update", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Updated.");

  await report.getByRole("link", { name: "8" }).click();
  // The highlight cuts the line into pieces, so look for the words either side of it.
  await expect(page.locator("main")).toContainText("solitary gray");
  await expect(page.locator("main")).not.toContainText("single");
  await expect(page.getByText("A bird worth watching.")).toBeVisible();
  await expect(page.locator(".hl")).toHaveText("heron");
});
