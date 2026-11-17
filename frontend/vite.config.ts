import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development Vite serves the app and proxies /api to the Python server.
// `npm run build` writes into the Python package, which then serves the files itself.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: {
    outDir: "../pneutext/web/dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
