// The thin fetch client. Everything the front end asks of the server goes through here,
// typed by schema.d.ts, which is generated from the server's OpenAPI schema.
import type { components } from "./schema";

export type LibraryInfo = components["schemas"]["LibraryOut"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `The server answered with an error (${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "PneuText's server is not responding. Is it still running?");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

export const api = {
  getLibrary: (): Promise<LibraryInfo> => request<LibraryInfo>("/api/library"),
};
