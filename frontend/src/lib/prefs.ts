// Small per-browser preferences (the reading mode now; level and type filters later).
// Remembered in localStorage when it is available, and harmless when it is not.
import { useSyncExternalStore } from "react";

export type Mode = "text" | "blank";

export interface Prefs {
  mode: Mode;
}

const KEY = "pneutext.prefs";
const DEFAULTS: Prefs = { mode: "text" };

function load(): Prefs {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "{}");
    if (typeof stored === "object" && stored !== null) {
      const mode = (stored as { mode?: unknown }).mode;
      return { mode: mode === "blank" ? "blank" : "text" };
    }
  } catch {
    // Storage is unavailable or holds something unreadable; use the defaults.
  }
  return DEFAULTS;
}

let current: Prefs | null = null;
const listeners = new Set<() => void>();

function snapshot(): Prefs {
  current ??= load();
  return current;
}

export function setPrefs(change: Partial<Prefs>): void {
  current = { ...snapshot(), ...change };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Not remembered between visits, but still applied for this one.
  }
  listeners.forEach((listener) => listener());
}

/** For tests: forget what is held in memory and read storage again. */
export function resetPrefs(): void {
  current = null;
  listeners.forEach((listener) => listener());
}

export function usePrefs(): Prefs {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, snapshot);
}
