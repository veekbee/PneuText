// A very small router over the History API: enough for a handful of stable URLs.
import { type MouseEvent, type ReactNode, useSyncExternalStore } from "react";

import { parseRoute, type Route } from "./lib/route";

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  window.addEventListener("hashchange", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
    window.removeEventListener("hashchange", listener);
  };
}

function currentUrl(): string {
  return window.location.pathname + window.location.hash;
}

export function navigate(to: string): void {
  if (to === currentUrl()) return;
  window.history.pushState(null, "", to);
  listeners.forEach((listener) => listener());
}

export function useRoute(): Route {
  const url = useSyncExternalStore(subscribe, currentUrl);
  const hashAt = url.indexOf("#");
  return hashAt === -1
    ? parseRoute(url)
    : parseRoute(url.slice(0, hashAt), url.slice(hashAt));
}

interface LinkProps {
  to: string;
  className?: string;
  children: ReactNode;
  "aria-current"?: "page" | "true";
  title?: string;
}

export function Link({ to, children, ...rest }: LinkProps) {
  function onClick(event: MouseEvent<HTMLAnchorElement>): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return; // let the browser open a new tab or window
    }
    event.preventDefault();
    navigate(to);
  }
  return (
    <a href={to} onClick={onClick} {...rest}>
      {children}
    </a>
  );
}
