import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The API runs on :8080 locally (set FIELDCARBON_API to point elsewhere); proxying keeps the browser on one origin, so no CORS setup is needed.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": loadEnv(mode, ".", "").FIELDCARBON_API || "http://127.0.0.1:8080" } },
}));
