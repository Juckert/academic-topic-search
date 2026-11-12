import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, process.cwd(), "");
  const apiMode = (process.env.VITE_SEARCH_MODE ?? environment.VITE_SEARCH_MODE) === "api";
  const localCatalog = resolve("src/fixtures/catalog.local.json");
  const catalog = !apiMode && existsSync(localCatalog) ? localCatalog : resolve("src/fixtures/catalog.json");
  return {
    plugins: [react()],
    resolve: { alias: { "@catalog": catalog } },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: false,
        },
      },
    },
    preview: { host: "127.0.0.1", port: 4173, strictPort: true },
    test: { environment: "node", include: ["src/**/*.test.ts"] },
  };
});
