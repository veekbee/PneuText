import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

test("export the monograph and a backup, neither holding the book's text", async ({ page }) => {
  const created = await page.request.post("/api/imports/corpus", {
    data: { folder: BOOK, work_code: "fx", title: "The Fixture Book", allow_duplicate: true },
  });
  const version = ((await created.json()) as { version_id: number }).version_id;
  await page.request.post(`/api/versions/${version}/imports/commentary`, {
    data: { folder: BOOK, page_ref_commands: ["pref"] },
  });
  const notes = (await (await page.request.get(`/api/versions/${version}/notes`)).json()) as { id: number }[];
  await page.request.post(`/api/versions/${version}/notes/status`, {
    data: { note_ids: notes.map((note) => note.id), status: "ready" },
  });

  // From the page, the Export button leads to the export view.
  await page.goto(`/v/${version}/p/7`);
  await page.getByRole("link", { name: "Export", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Export", level: 1 })).toBeVisible();

  await page.getByRole("combobox", { name: "Edition" }).selectOption({ label: "Full edition" });
  await expect(page.getByText(/Includes every note type; every reading level/)).toBeVisible();
  // Only the source here: building the PDF is covered by the backend's compile check.
  await page.getByLabel(/Build the PDF as well/).uncheck();
  await page.getByRole("button", { name: "Export the monograph" }).click();
  const result = page.getByRole("status", { name: "Export result" });
  await expect(result).toContainText(/Wrote \d+ files to .*fx-full-edition: 12 notes on 4 pages\./);

  const folder = ((await result.locator("code").first().textContent()) ?? "").trim();
  expect(existsSync(join(folder, "main.tex"))).toBe(true);
  const chapter = readFileSync(join(folder, "chapters", "chapter-01.tex"), "utf-8");
  expect(chapter).toContain("\\begin{pneupage}{7}");
  expect(chapter).toContain("\\pneunote{1}{Historical}");
  // The words the notes are attached to are nowhere in it.
  for (const words of ["kept his ledgers in a biscuit tin", "The ferry came into", "single heron stood"]) {
    expect(chapter).not.toContain(words);
  }

  await page.getByRole("button", { name: "Back up without the text" }).click();
  const backup = page.getByRole("status", { name: "Backup result" });
  await expect(backup).toContainText("contains no text of the book");
  const backupFolder = ((await backup.locator("code").textContent()) ?? "").trim();
  const library = readFileSync(join(backupFolder, "library.json"), "utf-8");
  expect(library).toContain('"includes_corpus_text": false');
  expect(library).not.toContain("The ferry came into");
});
