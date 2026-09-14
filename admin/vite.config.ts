import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Standalone deployment (Vercel) serves from "/".
  // Legacy note: the portal was once served by FastAPI under /admin
  // (see server/app/main.py); `vite dev` serves at http://localhost:5173/.
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
});
