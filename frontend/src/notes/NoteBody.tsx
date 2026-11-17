// Renders a parsed note body. Takes the syntax tree as plain data and never calls the
// API. Everything reaches the page as React text nodes: there is no raw HTML here.
import { createElement, type ReactNode } from "react";

import type { NoteNode } from "../api/client";

const SAFE_LINK = /^(https?:|mailto:)/i;

function children(node: NoteNode): ReactNode[] {
  return (node.children ?? []).map((child, index) => <Node key={index} node={child} />);
}

function Node({ node }: { node: NoteNode }): ReactNode {
  switch (node.type) {
    case "document":
      return <>{children(node)}</>;
    case "text":
      return node.text ?? "";
    case "paragraph":
      return <p>{children(node)}</p>;
    case "heading": {
      // Note headings sit below the app's own, whatever level the author typed.
      const level = Math.min(6, Math.max(3, Number(node.attrs?.level ?? 3) + 2));
      return createElement(`h${level}`, null, ...children(node));
    }
    case "blockquote":
      return <blockquote>{children(node)}</blockquote>;
    case "bullet_list":
      return <ul>{children(node)}</ul>;
    case "ordered_list":
      return <ol start={Number(node.attrs?.start ?? 1)}>{children(node)}</ol>;
    case "list_item":
      return <li>{children(node)}</li>;
    case "code_block":
      return (
        <pre>
          <code>{node.text ?? ""}</code>
        </pre>
      );
    case "thematic_break":
      return <hr />;
    case "emphasis":
      return <em>{children(node)}</em>;
    case "strong":
      return <strong>{children(node)}</strong>;
    case "code":
      return <code>{node.text ?? ""}</code>;
    case "softbreak":
      return " ";
    case "hardbreak":
      return <br />;
    case "link": {
      const href = String(node.attrs?.href ?? "");
      if (!SAFE_LINK.test(href)) return <>{children(node)}</>;
      return (
        <a href={href} title={String(node.attrs?.title ?? "") || undefined} rel="noreferrer noopener" target="_blank">
          {children(node)}
        </a>
      );
    }
    case "image":
      // Images are never fetched from elsewhere; only the description is shown.
      return <span className="note-image">[{String(node.attrs?.alt ?? "") || "image"}]</span>;
    default:
      // A node this version does not know keeps its words.
      return node.children ? <>{children(node)}</> : (node.text ?? "");
  }
}

export function NoteBody({ body }: { body: NoteNode }) {
  return (
    <div className="note-body">
      <Node node={body} />
    </div>
  );
}

/** Whether a parsed body has anything to show. */
export function isEmptyBody(body: NoteNode): boolean {
  return (body.children ?? []).length === 0;
}
