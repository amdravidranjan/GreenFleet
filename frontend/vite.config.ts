import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// css.postcss is set inline so Vite does not pick up a postcss.config from a parent folder.
export default defineConfig({
  plugins: [react()],
  css: { postcss: {} },
  // maplibre-gl spawns its own web worker; pre-bundling breaks the worker URL.
  optimizeDeps: { exclude: ["maplibre-gl"] },
});
