// A field that saves itself: type, then press Enter or leave the field.
import type { KeyboardEvent } from "react";

interface InlineEditProps {
  label: string;
  value: string;
  placeholder?: string;
  className?: string;
  onSave: (value: string) => void;
}

export function InlineEdit({ label, value, placeholder, className, onSave }: InlineEditProps) {
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key === "Enter") event.currentTarget.blur();
    if (event.key === "Escape") {
      event.currentTarget.value = value;
      event.currentTarget.blur();
    }
  }
  return (
    <input
      // A fresh field whenever the stored value changes, so it always shows what is saved.
      key={value}
      className={className ?? "inline-edit"}
      aria-label={label}
      defaultValue={value}
      placeholder={placeholder}
      onKeyDown={onKeyDown}
      onBlur={(event) => {
        if (event.target.value !== value) onSave(event.target.value);
      }}
    />
  );
}
