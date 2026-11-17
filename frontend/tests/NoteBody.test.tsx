import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { NoteNode } from "../src/api/client";
import { isEmptyBody, NoteBody } from "../src/notes/NoteBody";

afterEach(cleanup);

const text = (value: string): NoteNode => ({ type: "text", text: value });
const doc = (...children: NoteNode[]): NoteNode => ({ type: "document", children });
const para = (...children: NoteNode[]): NoteNode => ({ type: "paragraph", children });

describe("NoteBody", () => {
  it("renders paragraphs and inline formatting", () => {
    const { container } = render(
      <NoteBody
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
      <NoteBody body={doc(para(text('<img src=x onerror="alert(1)"> <b>bold</b>')))} />,
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
      <NoteBody body={doc(para(link("https://example.test/a")), para(link("javascript:alert(1)")))} />,
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
      <NoteBody body={doc(para({ type: "from_the_future", children: [text("kept")] }))} />,
    );
    expect(container.textContent).toBe("kept");
  });

  it("knows an empty body", () => {
    expect(isEmptyBody(doc())).toBe(true);
    expect(isEmptyBody(doc(para(text("x"))))).toBe(false);
  });
});
