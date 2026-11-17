// What points at the page: the notes that refer to it, and passages linked to it.
import type { Backlink, NoteType, PassageLink } from "../api/client";
import { pagePath } from "../lib/route";
import { Link } from "../router";

function place(page: number | null, line: number | null): string {
  if (page === null) return "";
  return line === null ? `p. ${page}` : `p. ${page}.${line}`;
}

export function BacklinkList({
  versionId,
  backlinks,
  types,
}: {
  versionId: number;
  backlinks: Backlink[];
  types: NoteType[];
}) {
  const typeName = new Map(types.map((type) => [type.id, type.name]));
  return (
    <ul className="backlinks">
      {backlinks.map((backlink, index) => (
        <li key={`${backlink.note_id}-${index}`}>
          {backlink.page === null ? (
            <span>{typeName.get(backlink.type_id) ?? "Note"}</span>
          ) : (
            <Link to={pagePath(versionId, backlink.page, backlink.line_no)}>
              {typeName.get(backlink.type_id) ?? "Note"}, {place(backlink.page, backlink.line_no)}
            </Link>
          )}
          {backlink.target && <span className="quiet"> cites {backlink.target}</span>}
        </li>
      ))}
    </ul>
  );
}

export function PassageLinkList({
  versionId,
  links,
  readOnly,
  onDelete,
}: {
  versionId: number;
  links: PassageLink[];
  readOnly: boolean;
  onDelete: (linkId: number) => void;
}) {
  return (
    <ul className="backlinks">
      {links.map((link) => {
        // Show the end that is on this page first, and link to the other.
        const [here, there] = link.source.here ? [link.source, link.target] : [link.target, link.source];
        return (
          <li key={link.id}>
            <span>{place(here.page, here.line_no)}</span>
            <span className="quiet"> ↔ </span>
            {there.page === null ? (
              <span>elsewhere</span>
            ) : (
              <Link to={pagePath(versionId, there.page, there.line_no)}>
                {place(there.page, there.line_no)}
              </Link>
            )}
            {!readOnly && (
              <button
                type="button"
                className="quiet-button"
                aria-label={`Remove the link to ${place(there.page, there.line_no)}`}
                onClick={() => onDelete(link.id)}
              >
                Remove
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
