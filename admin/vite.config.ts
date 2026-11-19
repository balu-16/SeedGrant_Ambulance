/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Standalone deployment (Vercel) serves from "/".
  // `vite dev` serves at http://localhost:5173/.
  base: "/",
  resolve: {
    alias: {
      // Mirrors the client app's "@/..." import style.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      // Local dev only — production (Vercel) calls VITE_API_URL directly.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  // Vitest unit tests (src/**/*.test.{ts,tsx}) — `test` config is read by the
  // vitest CLI from this same file. Playwright e2e live in playwright.config.ts.
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
