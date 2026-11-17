import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { NoteNode } from "../src/api/client";
import { isEmptyBody, NoteBody, type NoteEnv } from "../src/notes/NoteBody";

afterEach(cleanup);

const followed: string[] = [];
const ENV: NoteEnv = {
  pageHref: (versionId, page, line) => `/v/${versionId}/p/${page}${line == null ? "" : `#l${line}`}`,
  figureSrc: (label) => `/figures/${label}`,
  navigate: (href) => void followed.push(href),
};

const text = (value: string): NoteNode => ({ type: "text", text: value });
const doc = (...children: NoteNode[]): NoteNode => ({ type: "document", children });
const para = (...children: NoteNode[]): NoteNode => ({ type: "paragraph", children });

describe("NoteBody", () => {
  it("renders paragraphs and inline formatting", () => {
    const { container } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para(
            text("Plain "),
            { type: "emphasis", children: [text("soft")] },
            text(" "),
            { type: "strong", children: [text("loud")] },
            text(" "),
            { type: "code", text: "x = 1" },
          ),
        )}
      />,
    );
    expect(container.querySelector("p")?.textContent).toBe("Plain soft loud x = 1");
    expect(container.querySelector("em")?.textContent).toBe("soft");
    expect(container.querySelector("strong")?.textContent).toBe("loud");
    expect(container.querySelector("code")?.textContent).toBe("x = 1");
  });

  it("renders block structure", () => {
    const { container } = render(
      <NoteBody
        env={ENV}
        body={doc(
          { type: "heading", attrs: { level: 1 }, children: [text("Title")] },
          { type: "blockquote", children: [para(text("said"))] },
          { type: "bullet_list", children: [{ type: "list_item", children: [para(text("a"))] }] },
          {
            type: "ordered_list",
            attrs: { start: 3 },
            children: [{ type: "list_item", children: [para(text("c"))] }],
          },
          { type: "code_block", attrs: { info: "" }, text: "line\n" },
          { type: "thematic_break" },
        )}
      />,
    );
    // A note's top heading sits below the app's own headings.
    expect(container.querySelector("h3")?.textContent).toBe("Title");
    expect(container.querySelector("blockquote p")?.textContent).toBe("said");
    expect(container.querySelector("ul li")?.textContent).toBe("a");
    expect(container.querySelector("ol")?.getAttribute("start")).toBe("3");
    expect(container.querySelector("pre code")?.textContent).toBe("line\n");
    expect(container.querySelector("hr")).not.toBeNull();
  });

  it("shows markup-looking text as text, never as elements", () => {
    const { container } = render(
      <NoteBody env={ENV} body={doc(para(text('<img src=x onerror="alert(1)"> <b>bold</b>')))} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>bold</b>");
  });

  it("links only to web and mail addresses, and opens them safely", () => {
    const link = (href: string): NoteNode => ({
      type: "link",
      attrs: { href, title: "" },
      children: [text("here")],
    });
    const { container } = render(
      <NoteBody env={ENV} body={doc(para(link("https://example.test/a")), para(link("javascript:alert(1)")))} />,
    );
    const anchors = container.querySelectorAll("a");
    expect(anchors.length).toBe(1);
    expect(anchors[0]?.getAttribute("href")).toBe("https://example.test/a");
    expect(anchors[0]?.getAttribute("rel")).toContain("noopener");
    expect(container.textContent).toBe("herehere");
  });

  it("never loads an image; it shows the description instead", () => {
    const { container } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para({ type: "image", attrs: { src: "https://example.test/p.png", alt: "a map", title: "" } }),
        )}
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("[a map]");
  });

  it("keeps the words of a node it does not know", () => {
    const { container } = render(
      <NoteBody env={ENV} body={doc(para({ type: "from_the_future", children: [text("kept")] }))} />,
    );
    expect(container.textContent).toBe("kept");
  });

  it("knows an empty body", () => {
    expect(isEmptyBody(doc())).toBe(true);
    expect(isEmptyBody(doc(para(text("x"))))).toBe(false);
  });
});

describe("NoteBody: PneuText's own forms", () => {
  it("renders a resolved reference as a link that shows the page and leads to it", () => {
    const { getByRole } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para({
            type: "reference",
            text: "{{fx:10.3}}",
            attrs: { work: "fx", target: "10.3", label: "p. 10.3", broken: false, version_id: 2, page: 10, line: 3 },
          }),
        )}
      />,
    );
    const link = getByRole("link", { name: "p. 10.3" });
    expect(link.getAttribute("href")).toBe("/v/2/p/10#l3");
    followed.length = 0;
    fireEvent.click(link);
    expect(followed).toEqual(["/v/2/p/10#l3"]);
  });

  it("keeps a broken reference visible as it was typed", () => {
    const { container, queryByRole } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para(
            { type: "reference", text: "{{fx:99}}", attrs: { work: "fx", target: "99", broken: true } },
            text(" "),
            { type: "note_ref", text: "{{note:7}}", attrs: { id: 7, broken: true } },
            text(" "),
            { type: "broken", text: "{{nope}}" },
            text(" "),
            { type: "unsupported", text: "{{cite:k}}", attrs: { form: "cite", key: "k" } },
          ),
        )}
      />,
    );
    expect(queryByRole("link")).toBeNull();
    expect([...container.querySelectorAll(".broken")].map((item) => item.textContent)).toEqual([
      "{{fx:99}}",
      "{{note:7}}",
      "{{nope}}",
      "{{cite:k}}",
    ]);
  });

  it("links a reference to a note to the page the note is on", () => {
    const { getByRole } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para({
            type: "note_ref",
            text: "{{note:7}}",
            attrs: { id: 7, broken: false, version_id: 2, page: 7, line: 5, type_id: 1, level: 1 },
          }),
        )}
      />,
    );
    expect(getByRole("link", { name: "note on p. 7" }).getAttribute("href")).toBe("/v/2/p/7#l5");
  });

  it("places a figure from the library with its caption and credit", () => {
    const { container } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para({
            type: "figure",
            attrs: { label: "harbor", caption: "The harbor", credit: "A. Quill", file: "harbor.png", broken: false },
          }),
          para({ type: "figure", attrs: { label: "lost", caption: "Missing", broken: true } }),
          para({ type: "figure_ref", text: "{{fig:harbor}}", attrs: { label: "harbor", caption: "The harbor", broken: false } }),
        )}
      />,
    );
    const image = container.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/figures/harbor");
    expect(image?.getAttribute("alt")).toBe("The harbor");
    expect(container.querySelector("figcaption")?.textContent).toBe("The harbor A. Quill");
    expect(container.querySelectorAll("img").length).toBe(1); // the missing figure loads nothing
    expect(container.querySelector(".figure-ref")?.textContent).toBe("fig. harbor");
  });

  it("shows a gloss as the word with its meaning", () => {
    const { container } = render(
      <NoteBody
        env={ENV}
        body={doc(para({ type: "gloss", text: "", attrs: { word: "camino", meaning: "road, way" } }))}
      />,
    );
    expect(container.querySelector(".gloss")?.textContent).toBe("camino (road, way)");
    expect(container.querySelector(".gloss i")?.textContent).toBe("camino");
  });

  it("shows the narrative date and elapsed time worked out for the note's place", () => {
    const { container } = render(
      <NoteBody
        env={ENV}
        body={doc(
          para(
            text("It is "),
            { type: "when", text: "{{when}}", attrs: { value: "3 March 1872", broken: false } },
            text(", "),
            { type: "since", text: "{{since:arrival}}", attrs: { label: "arrival", value: "2 days", broken: false } },
            text(" on; "),
            { type: "since", text: "{{since:nowhere}}", attrs: { label: "nowhere", broken: true } },
          ),
        )}
      />,
    );
    expect(container.textContent).toBe("It is 3 March 1872, 2 days on; {{since:nowhere}}");
    expect([...container.querySelectorAll(".narrative-time")].map((item) => item.textContent)).toEqual([
      "3 March 1872",
      "2 days",
    ]);
    expect(container.querySelector(".broken")?.textContent).toBe("{{since:nowhere}}");
  });

  it("sets an editorial remark apart", () => {
    const { container } = render(
      <NoteBody env={ENV} body={doc(para(text("A note.")), { type: "todo", children: [text("check the date")] })} />,
    );
    expect(container.querySelector("aside.todo")?.textContent).toBe("To do check the date");
  });
});
