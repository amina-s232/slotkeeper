import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development every /api request is forwarded to Django, so the browser sees ONE origin.
// No CORS preflights, and the code that runs in production (relative "/api") is the code you test.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": backend } },
  preview: { port: 4173, proxy: { "/api": backend } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
