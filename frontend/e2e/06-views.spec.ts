import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

const BOOK = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "tests", "fixtures", "book");

/** A fresh copy of the fixture book with its old commentary imported. */
async function library(page: Page): Promise<number> {
  const created = await page.request.post("/api/imports/corpus", {
    data: { folder: BOOK, work_code: "fx", title: "The Fixture Book", allow_duplicate: true },
  });
  const version = ((await created.json()) as { version_id: number }).version_id;
  const imported = await page.request.post(`/api/versions/${version}/imports/commentary`, {
    data: { folder: BOOK, page_ref_commands: ["pref"] },
  });
  expect(imported.status()).toBe(201);
  return version;
}

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

test("entities: mentions are underlined, a selection is tagged, and the index lists pages", async ({
  page,
}) => {
  const version = await library(page);
  await page.goto(`/v/${version}/p/8`);

  // Imported mentions show as a thin underline, which can be switched off.
  await expect(page.locator("#l3 .mention")).toHaveText("heron");
  await expect(page.locator(".page-body .mention")).toHaveCount(6);
  await page.getByLabel("Underline entities").uncheck();
  await expect(page.locator(".page-body .mention")).toHaveCount(0);
  await page.getByLabel("Underline entities").check();

  // The sidebar counts the notes in each chapter.
  await expect(page.getByRole("link", { name: /^I\s*15\s*p\. 7$/ })).toBeVisible();

  // Tag a place: a new entity, named by the words selected.
  await select(page, 2, "marsh");
  const popover = page.getByRole("dialog", { name: "Selection" });
  await popover.getByRole("button", { name: "Tag entity" }).click();
  const form = popover.getByRole("form", { name: "Tag entity" });
  await expect(form.getByLabel("Entity")).toHaveValue("marsh");
  await form.getByLabel("Entity").fill("the marsh");
  await form.getByRole("button", { name: "Tag", exact: true }).click();
  await expect(popover).toHaveCount(0);
  await expect(page.locator("#l2 .mention")).toHaveText(["marsh", "Reeds"]);

  // The index: each category's entities with every page they occur on.
  await page.getByRole("link", { name: "Entities", exact: true }).click();
  const places = page.getByRole("region", { name: "places" });
  await expect(places.getByLabel("Name of Low Harbor")).toHaveValue("Low Harbor");
  await expect(places.getByRole("row").nth(1).getByRole("link")).toHaveText(["7", "7"]);
  await expect(places.getByLabel("Name of the marsh")).toBeVisible();
  const numbers = page.getByRole("region", { name: "numbers" });
  await expect(numbers.getByLabel("Value of forty-six")).toHaveValue("46");
  await expect(page.getByRole("region", { name: "weather" })).toBeVisible(); // created by the import

  // Rename and merge; the index follows.
  await places.getByLabel("Name of the marsh").fill("The Marsh");
  await places.getByLabel("Name of The Marsh").blur();
  await expect(places.getByLabel("Name of The Marsh")).toHaveValue("The Marsh");
  const animals = page.getByRole("region", { name: "animals" });
  await animals.getByLabel("Merge eels into").selectOption({ label: "gulls" });
  await expect(animals.getByLabel("Name of eels")).toHaveCount(0);
  await expect(animals.getByRole("row").filter({ has: page.getByLabel("Name of gulls") }).getByRole("link")).toHaveText(["7", "8"]);

  // A page link in the index opens the text at that line.
  await numbers.getByRole("row").filter({ has: page.getByLabel("Name of forty-six") }).getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/9#l4$`));
});

test("narrative time: values resolve down the chain, and notes show the date at their place", async ({
  page,
}) => {
  const version = await library(page);
  await page.goto(`/v/${version}/chronology`);

  // Two time tags came from the import, without values.
  const rows = page.getByRole("table").getByRole("row");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(1)).toContainText("No value has been given yet.");

  const first = page.getByRole("form", { name: "Time at 7.4" });
  await first.getByRole("combobox", { name: "Kind", exact: true }).selectOption("absolute");
  await first.getByRole("textbox", { name: "Date", exact: true }).fill("1871-10-28");
  await first.getByRole("textbox", { name: "Label", exact: true }).fill("arrival");
  await first.getByRole("button", { name: "Save" }).click();
  await expect(rows.nth(1)).toContainText("28 October 1871");

  const second = page.getByRole("form", { name: "Time at 8.7" });
  await second.getByRole("combobox", { name: "Kind", exact: true }).selectOption("offset");
  await second.getByRole("textbox", { name: "Offset", exact: true }).fill("P2D");
  await second.getByRole("button", { name: "Save" }).click();
  await expect(rows.nth(2)).toContainText("30 October 1871");
  await expect(rows.nth(2)).toContainText("2 days since arrival");

  // Correcting the first value moves the second at once.
  await first.getByRole("textbox", { name: "Date", exact: true }).fill("1872-03-01");
  await first.getByRole("button", { name: "Save" }).click();
  await expect(rows.nth(2)).toContainText("3 March 1872");

  // A bad value is explained, not saved.
  await second.getByRole("textbox", { name: "Offset", exact: true }).fill("two days");
  await second.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert")).toContainText("Write the offset as a duration");

  // A note's {{when}} and {{since:label}} are worked out for its place in the text.
  const types = (await (await page.request.get("/api/note-types")).json()) as { id: number; name: string }[];
  const text = (await (await page.request.get(`/api/versions/${version}/pages/9/text`)).json()) as {
    lines: { line_no: number | null; segment_id: number; start_offset: number; text: string }[];
  };
  const line = text.lines.find((item) => item.line_no === 1);
  if (!line) throw new Error("no first line on page 9");
  await page.request.post(`/api/versions/${version}/notes`, {
    data: {
      type_id: types.find((type) => type.name === "Comment")?.id,
      body_md: "It is {{when}}, {{since:arrival}} after landing.",
      span: {
        start_segment_id: line.segment_id,
        start_offset: line.start_offset,
        end_segment_id: line.segment_id,
        end_offset: line.start_offset + 4,
        exact: line.text.slice(0, 4),
      },
    },
  });
  await page.goto(`/v/${version}/p/9`);
  await expect(page.locator(".note-card").first()).toContainText(
    "It is 3 March 1872, 2 days after landing.",
  );
});

test("figures, review, to-do and note types are filled from the library", async ({ page }) => {
  const version = await library(page);

  // Figures: where each is used; a missing image can be uploaded; an unused one is flagged.
  await page.goto(`/v/${version}/figures`);
  const harbor = page.getByRole("listitem", { name: "Figure harbor" });
  await expect(harbor.getByRole("img")).toBeVisible();
  await expect(harbor.getByRole("link").last()).toHaveText("p. 7");
  const chain = page.getByRole("listitem", { name: "Figure chain" });
  await expect(chain).toContainText("No image yet");
  await chain.getByLabel("Image for chain").setInputFiles(join(BOOK, "harbor.png"));
  await expect(chain.getByRole("img")).toBeVisible();
  const loaded = await chain.getByRole("img").evaluate((image: HTMLImageElement) => image.naturalWidth);
  expect(loaded).toBeGreaterThan(0);

  const fresh = `spare-${version}`;
  const added = page.getByRole("form", { name: "New figure" });
  await added.getByRole("textbox", { name: "Label", exact: true }).fill(fresh);
  await added.getByRole("textbox", { name: "Caption", exact: true }).fill("Never placed");
  await added.getByRole("button", { name: "Add figure" }).click();
  await expect(page.getByRole("listitem", { name: `Figure ${fresh}` })).toContainText("Unused");

  // Review: filter, then mark in bulk.
  await page.getByRole("link", { name: "Review", exact: true }).click();
  const bulk = page.getByRole("group", { name: "Selected notes" });
  await expect(bulk).toContainText("16 notes");
  const filters = page.getByRole("group", { name: "Filters" });
  await filters.getByRole("combobox", { name: "Type", exact: true }).selectOption({ label: "Historical" });
  await expect(bulk).toContainText("3 notes");
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(4);
  await bulk.getByRole("button", { name: "Select all" }).click();
  await bulk.getByRole("button", { name: "Mark ready" }).click();
  await expect(page.getByRole("table").getByRole("row").nth(1)).toContainText("Ready");
  await filters.getByRole("combobox", { name: "Type", exact: true }).selectOption("");
  await filters.getByRole("combobox", { name: "Status", exact: true }).selectOption("draft");
  await expect(bulk).toContainText("13 notes");
  await filters.getByRole("combobox", { name: "Chapter", exact: true }).selectOption({ label: "II" });
  await expect(bulk).toContainText("1 note");

  // To-do: remarks, times without a value, the unused figure, the remaining drafts.
  await page.getByRole("link", { name: "To-do", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Remarks (6)" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Remarks" })).toContainText(
    "check the make of the theodolite",
  );
  await expect(page.getByRole("heading", { name: "Times without a value (2)" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Unused figures" })).toContainText(fresh);
  await expect(page.getByRole("heading", { name: "Draft notes (13)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Broken references (0)" })).toBeVisible();
  // An entry leads to its page.
  await page.getByRole("region", { name: "Remarks" }).getByRole("link").nth(1).click();
  await expect(page).toHaveURL(new RegExp(`/v/${version}/p/7#l5$`));

  // Note types: listed, and a new one can be added and then merged away.
  await page.getByRole("link", { name: "Note types", exact: true }).click();
  await expect(page.getByLabel("Name of Clarification")).toBeVisible();
  const code = `g${version}`;
  const newType = page.getByRole("form", { name: "New note type" });
  await newType.getByRole("textbox", { name: "Name", exact: true }).fill(`Geography ${version}`);
  await newType.getByRole("textbox", { name: "Code", exact: true }).fill(code);
  await newType.getByRole("button", { name: "Add note type" }).click();
  await expect(page.getByLabel(`Name of Geography ${version}`)).toBeVisible();
  await page.getByLabel(`Merge Geography ${version} into`).selectOption({ label: "Comment" });
  await expect(page.getByLabel(`Name of Geography ${version}`)).toHaveCount(0);

  if (process.env.SHOT) {
    await page.setViewportSize({ width: 1400, height: 900 });
    for (const view of ["entities", "chronology", "figures", "review", "todo"]) {
      await page.goto(`/v/${version}/${view}`);
      await page.getByRole("heading", { level: 1 }).waitFor();
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${process.env.SHOT}-${view}.png` });
    }
  }
});
