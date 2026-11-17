// The to-do list: every TODO remark, draft note, broken reference, orphaned anchor,
// unused figure and time without a value.
import type { ReactNode } from "react";

import type { NoteSummary } from "../api/client";
import { useNoteTypes, useTodoList } from "../api/queries";
import { pagePath, viewPath } from "../lib/route";
import { Link } from "../router";
import { Loading, VersionShell } from "../shell/VersionShell";
import { placeOf } from "./ReviewView";

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="todo-section" aria-label={title}>
      <h2>
        {title} <span className="quiet">({count})</span>
      </h2>
      {count === 0 ? <p className="quiet">Nothing here.</p> : <ul>{children}</ul>}
    </section>
  );
}

export function TodoView({ versionId }: { versionId: number }) {
  const todo = useTodoList(versionId);
  const types = useNoteTypes();
  const typeName = new Map((types.data ?? []).map((type) => [type.id, type.name]));

  function where(note: NoteSummary): ReactNode {
    const label = `${typeName.get(note.type_id) ?? "Note"}, ${placeOf(note)}`;
    return note.page === null ? label : <Link to={pagePath(versionId, note.page, note.line_no)}>{label}</Link>;
  }

  const found = todo.data;
  return (
    <VersionShell versionId={versionId} view="todo" title="To-do">
      {found === undefined ? (
        <Loading error={todo.error} />
      ) : (
        <>
          <Section title="Remarks" count={found.remarks.length}>
            {found.remarks.map((remark, index) => (
              <li key={index}>
                {where(remark.note)}: {remark.text}
              </li>
            ))}
          </Section>
          <Section title="Times without a value" count={found.times_without_value.length}>
            {found.times_without_value.map((time) => (
              <li key={time.mention_id}>
                {time.page === null ? (
                  "A time"
                ) : (
                  <Link to={pagePath(versionId, time.page, time.line_no)}>{placeOf(time)}</Link>
                )}
                : give it a date in the <Link to={viewPath(versionId, "chronology")}>chronology</Link>
              </li>
            ))}
          </Section>
          <Section title="Broken references" count={found.broken_references.length}>
            {found.broken_references.map((broken, index) => (
              <li key={index}>
                {where(broken.note)}: <code>{broken.form}</code>
              </li>
            ))}
          </Section>
          <Section title="Notes that lost their place" count={found.orphaned.length}>
            {found.orphaned.map((note) => (
              <li key={note.id}>
                {where(note)}: {note.excerpt}
              </li>
            ))}
          </Section>
          <Section title="Unused figures" count={found.unused_figures.length}>
            {found.unused_figures.map((figure) => (
              <li key={figure.id}>
                <Link to={viewPath(versionId, "figures")}>{figure.label}</Link>
                {figure.caption && `: ${figure.caption}`}
              </li>
            ))}
          </Section>
          <Section title="Draft notes" count={found.drafts.length}>
            {found.drafts.map((note) => (
              <li key={note.id}>
                {where(note)}
                {note.excerpt && `: ${note.excerpt}`}
              </li>
            ))}
          </Section>
        </>
      )}
    </VersionShell>
  );
}
