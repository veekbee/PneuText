// Renders a parsed note body. Takes the syntax tree as plain data and never calls the
// API. Everything reaches the page as React text nodes: there is no raw HTML here.
//
// Where a reference leads, and where a figure's image comes from, are given by the
// surroundings (`NoteEnv`), so a static edition can render the same tree its own way.
import { createElement, type MouseEvent, type ReactNode } from "react";

import type { NoteNode } from "../api/client";

export interface NoteEnv {
  /** The address of a page, or of a line on it. */
  pageHref: (versionId: number, page: number, line?: number | null) => string;
  /** The address of a figure's image. */
  figureSrc: (label: string) => string;
  /** Follow an address within the app. */
  navigate: (href: string) => void;
}

const SAFE_LINK = /^(https?:|mailto:)/i;

function Internal({ href, env, children }: { href: string; env: NoteEnv; children: ReactNode }) {
  function onClick(event: MouseEvent<HTMLAnchorElement>): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    env.navigate(href);
  }
  return (
    <a className="ref" href={href} onClick={onClick}>
      {children}
    </a>
  );
}

function Broken({ text, why }: { text: string; why: string }) {
  return (
    <span className="broken" title={why}>
      {text}
    </span>
  );
}

function number(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function Node({ node, env }: { node: NoteNode; env: NoteEnv }): ReactNode {
  const children = (): ReactNode[] =>
    (node.children ?? []).map((child, index) => <Node key={index} node={child} env={env} />);
  const attrs = node.attrs ?? {};

  switch (node.type) {
    case "document":
      return <>{children()}</>;
    case "text":
      return node.text ?? "";
    case "paragraph":
      return <p>{children()}</p>;
    case "heading": {
      // Note headings sit below the app's own, whatever level the author typed.
      const level = Math.min(6, Math.max(3, Number(attrs.level ?? 3) + 2));
      return createElement(`h${level}`, null, ...children());
    }
    case "blockquote":
      return <blockquote>{children()}</blockquote>;
    case "bullet_list":
      return <ul>{children()}</ul>;
    case "ordered_list":
      return <ol start={Number(attrs.start ?? 1)}>{children()}</ol>;
    case "list_item":
      return <li>{children()}</li>;
    case "code_block":
      return (
        <pre>
          <code>{node.text ?? ""}</code>
        </pre>
      );
    case "thematic_break":
      return <hr />;
    case "emphasis":
      return <em>{children()}</em>;
    case "strong":
      return <strong>{children()}</strong>;
    case "code":
      return <code>{node.text ?? ""}</code>;
    case "softbreak":
      return " ";
    case "hardbreak":
      return <br />;
    case "link": {
      const href = String(attrs.href ?? "");
      if (!SAFE_LINK.test(href)) return <>{children()}</>;
      return (
        <a href={href} title={String(attrs.title ?? "") || undefined} rel="noreferrer noopener" target="_blank">
          {children()}
        </a>
      );
    }
    case "image":
      // Images are never fetched from elsewhere; only the description is shown.
      return <span className="note-image">[{String(attrs.alt ?? "") || "image"}]</span>;

    // ---- PneuText's own forms ----
    case "reference": {
      const versionId = number(attrs.version_id);
      const page = number(attrs.page);
      if (attrs.broken !== false || versionId === null || page === null) {
        return <Broken text={node.text ?? ""} why="This reference leads nowhere" />;
      }
      return (
        <Internal href={env.pageHref(versionId, page, number(attrs.line))} env={env}>
          {String(attrs.label ?? node.text ?? "")}
        </Internal>
      );
    }
    case "note_ref": {
      const versionId = number(attrs.version_id);
      const page = number(attrs.page);
      if (attrs.broken !== false || versionId === null || page === null) {
        return <Broken text={node.text ?? ""} why="The note this refers to no longer exists" />;
      }
      return (
        <Internal href={env.pageHref(versionId, page, number(attrs.line))} env={env}>
          note on p. {page}
        </Internal>
      );
    }
    case "figure": {
      const label = String(attrs.label ?? "");
      const caption = String(attrs.caption ?? "");
      const credit = String(attrs.credit ?? "");
      return (
        <figure className="note-figure">
          {attrs.broken === false ? (
            <img src={env.figureSrc(label)} alt={caption || label} />
          ) : (
            <Broken text={`![${caption}](fig:${label})`} why="No figure has this label" />
          )}
          {(caption || credit) && (
            <figcaption>
              {caption}
              {credit && <span className="quiet"> {credit}</span>}
            </figcaption>
          )}
        </figure>
      );
    }
    case "figure_ref":
      if (attrs.broken !== false) {
        return <Broken text={node.text ?? ""} why="No figure has this label" />;
      }
      return (
        <span className="ref figure-ref" title={String(attrs.caption ?? "")}>
          fig. {String(attrs.label ?? "")}
        </span>
      );
    case "gloss": {
      const meaning = String(attrs.meaning ?? "");
      return (
        <span className="gloss">
          <i>{String(attrs.word ?? "")}</i>
          {meaning && ` (${meaning})`}
        </span>
      );
    }
    case "when":
    case "since":
      // The narrative date at the note's place, or the time elapsed there since a
      // labeled point. Worked out by the server each time the note is shown.
      if (attrs.broken !== false || typeof attrs.value !== "string") {
        const why =
          node.type === "when"
            ? "No time before this place in the text has a value"
            : "The time elapsed since that label cannot be worked out here";
        return <Broken text={node.text ?? ""} why={why} />;
      }
      return <span className="narrative-time">{attrs.value}</span>;
    case "todo":
      // An editorial remark: shown here, listed among the to-dos, never exported.
      return (
        <aside className="todo">
          <strong>To do</strong> {children()}
        </aside>
      );
    case "unsupported":
      return <Broken text={node.text ?? ""} why="Citations are not supported yet" />;
    case "broken":
      return <Broken text={node.text ?? ""} why="This form is not understood" />;
    default:
      // A node this version does not know keeps its words.
      return node.children ? <>{children()}</> : (node.text ?? "");
  }
}

export function NoteBody({ body, env }: { body: NoteNode; env: NoteEnv }) {
  return (
    <div className="note-body">
      <Node node={body} env={env} />
    </div>
  );
}

/** Whether a parsed body has anything to show. */
export function isEmptyBody(body: NoteNode): boolean {
  return (body.children ?? []).length === 0;
}
