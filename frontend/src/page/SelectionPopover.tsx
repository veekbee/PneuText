// What can be done with a selection: Note, Highlight, Copy reference, and carrying the
// selection on to the next page. (Tag entity and Link join in later milestones.)
import { type CSSProperties, useState } from "react";

import type { NoteType } from "../api/client";

interface SelectionPopoverProps {
  rect: { left: number; top: number; bottom: number; width: number };
  types: NoteType[];
  /** The type used when none is picked: the one used last. */
  defaultType: number | null;
  reference: string;
  canContinue: boolean;
  onNote: (typeId: number) => void;
  onHighlight: (typeId: number) => void;
  onCopied: () => void;
  onContinue: () => void;
}

export function SelectionPopover(props: SelectionPopoverProps) {
  const [choosing, setChoosing] = useState<"note" | "highlight" | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  const style: CSSProperties = {
    left: Math.max(8, props.rect.left + props.rect.width / 2),
    top: props.rect.bottom + 8,
  };

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(props.reference);
      props.onCopied();
    } catch {
      setCopyFailed(true); // show the reference so it can be copied by hand
    }
  }

  function pick(typeId: number): void {
    if (choosing === "highlight") props.onHighlight(typeId);
    else props.onNote(typeId);
  }

  return (
    <div
      className="popover"
      role="dialog"
      aria-label="Selection"
      style={style}
      // Keep the page's selection while the popover is used.
      onMouseDown={(event) => event.preventDefault()}
    >
      {choosing === null ? (
        <div className="popover-actions">
          <button type="button" onClick={() => setChoosing("note")} title="New note (n)">
            Note
          </button>
          <button type="button" onClick={() => setChoosing("highlight")} title="Highlight only (h)">
            Highlight
          </button>
          <button type="button" onClick={() => void copy()}>
            Copy reference
          </button>
          {props.canContinue && (
            <button type="button" onClick={props.onContinue} title="The passage runs on to the next page">
              Continue on next page
            </button>
          )}
        </div>
      ) : (
        <div className="popover-types" role="group" aria-label="Note type">
          {props.types.map((type) => (
            <button
              key={type.id}
              type="button"
              className="type-toggle"
              aria-pressed={type.id === props.defaultType}
              style={{ "--type-color": type.color } as CSSProperties}
              onClick={() => pick(type.id)}
            >
              {type.name}
            </button>
          ))}
        </div>
      )}
      {copyFailed && <code className="popover-reference">{props.reference}</code>}
    </div>
  );
}
