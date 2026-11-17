// The report of a legacy commentary import: what was found, what was repaired, and
// every problem grouped by kind. Plain data in; it never calls the API.
import type { LegacyReport, ReportItem } from "../api/client";

function Items({ items }: { items: ReportItem[] }) {
  return (
    <ul className="problems">
      {items.map((item, index) => (
        <li key={index}>{item.message}</li>
      ))}
    </ul>
  );
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function LegacyReportView({ report }: { report: LegacyReport }) {
  const problems = report.groups.reduce((total, group) => total + group.items.length, 0);
  const counts: [string, number][] = [
    ["Files", report.files],
    ["Notes", report.notes],
    ["Flagged", report.flagged_notes],
    ["Chapter notes", report.chapter_notes],
    ["Remarks", report.remarks],
    ["Entity mentions", report.mentions],
    ["Figures", report.figures],
    ["Problems", problems],
    ["Repairs", report.repairs.length],
  ];
  return (
    <section aria-labelledby="report-title" className="import-summary">
      <h2 id="report-title">What was found</h2>
      <dl className="counts">
        {counts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="quiet">
        Every note arrives as a draft. Flagged notes carry a to-do saying what to check.
      </p>
      {report.new_categories.length > 0 && (
        <p>
          New {report.new_categories.length === 1 ? "category" : "categories"}:{" "}
          {report.new_categories.join(", ")}.
        </p>
      )}
      {report.replaced_notes + report.replaced_mentions > 0 && (
        <div role="alert" className="notice">
          <p>
            These pages were imported before. Importing again replaces{" "}
            {plural(report.replaced_notes, "note", "notes")} and{" "}
            {plural(report.replaced_mentions, "mention", "mentions")} that came from the
            files, including any changes made to them since. Notes made in the app are kept.
          </p>
        </div>
      )}
      {report.groups.map((group) => (
        <section key={group.code} aria-label={group.title} className="report-group">
          <h3>
            {group.title} <span className="quiet">({group.items.length})</span>
          </h3>
          <Items items={group.items} />
        </section>
      ))}
      {report.repairs.length > 0 && (
        <section aria-label="Repairs" className="report-group">
          <h3>
            Repaired <span className="quiet">({report.repairs.length})</span>
          </h3>
          <Items items={report.repairs} />
        </section>
      )}
    </section>
  );
}
