// The left sidebar: chapters with their note counts, and below them the views.
import type { Division, Version } from "../api/client";
import { pagePath, type ViewName, viewPath } from "../lib/route";
import { Link } from "../router";

const VIEW_LABELS: [ViewName, string][] = [
  ["review", "Review"],
  ["todo", "To-do"],
  ["entities", "Entities"],
  ["chronology", "Chronology"],
  ["figures", "Figures"],
  ["types", "Note types"],
  ["export", "Export"],
];

interface SidebarProps {
  version: Version | undefined;
  /** The chapter the page being read belongs to. */
  currentDivision?: Division | null;
  currentView?: ViewName;
}

export function Sidebar({ version, currentDivision = null, currentView }: SidebarProps) {
  const chapters = version?.divisions.filter((division) => division.page !== null) ?? [];
  return (
    <aside className="sidebar" aria-label="Chapters and views">
      <h2>Chapters</h2>
      {version && chapters.length === 0 && <p className="quiet">This text has no chapters.</p>}
      <ol className="chapter-list">
        {version &&
          chapters.map((division) => (
            <li key={division.id}>
              <Link
                to={pagePath(version.id, division.page as number)}
                aria-current={currentDivision?.id === division.id ? "true" : undefined}
              >
                <span className="chapter-label">{division.label}</span>
                {division.note_count > 0 && (
                  <span
                    className="chapter-count"
                    title={`${division.note_count} ${division.note_count === 1 ? "note" : "notes"}`}
                  >
                    {division.note_count}
                  </span>
                )}
                <span className="chapter-page">p. {division.page}</span>
              </Link>
            </li>
          ))}
      </ol>
      <h2>Views</h2>
      <ul className="view-list">
        {version &&
          VIEW_LABELS.map(([view, label]) => (
            <li key={view}>
              <Link
                to={viewPath(version.id, view)}
                aria-current={currentView === view ? "page" : undefined}
              >
                {label}
              </Link>
            </li>
          ))}
      </ul>
    </aside>
  );
}
