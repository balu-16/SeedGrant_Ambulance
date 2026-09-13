import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The built portal is served by FastAPI under /admin (see server/app/main.py);
  // `vite dev` then also serves the app at http://localhost:5173/admin/.
  base: "/admin/",
  resolve: {
    alias: {
      // Mirrors the client app's "@/..." import style.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      // The portal calls the same FastAPI backend as the driver app.
      // Dev only — in production the built portal is mounted at /admin on
      // the FastAPI origin itself (see README).
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
