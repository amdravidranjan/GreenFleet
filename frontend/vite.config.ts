import { copyFileSync, mkdirSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// maplibre-gl v6 loads its web worker from a module file next to its own bundle, which Vite does
// not emit. Copy the worker (and the shared chunk it imports) into dist/maplibre/; FleetMap points
// setWorkerUrl() at it in production builds.
function maplibreWorker(): Plugin {
  return {
    name: "maplibre-worker",
    apply: "build",
    closeBundle() {
      mkdirSync("dist/maplibre", { recursive: true });
      for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
        copyFileSync(`node_modules/maplibre-gl/dist/${f}`, `dist/maplibre/${f}`);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), maplibreWorker()],
  base: "./", // relative asset URLs: the same build works on Vercel and on GitHub Pages (/GreenFleet/)
  // css.postcss is set inline so Vite does not pick up a postcss.config from a parent folder.
  css: { postcss: {} },
  // maplibre-gl spawns its own web worker; pre-bundling breaks the worker URL in dev.
  optimizeDeps: { exclude: ["maplibre-gl"] },
});
