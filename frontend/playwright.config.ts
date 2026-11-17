import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// End-to-end tests run against the real server with a throwaway library.
// Run `npm run e2e`, which builds the front end first.
const PORT = 8791;
const library = join(tmpdir(), "pneutext-e2e-library");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  webServer: {
    command: `rm -rf "${library}" && uv run pneutext --library "${library}" --port ${PORT} --no-browser`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/library`,
    reuseExistingServer: false,
  },
});
