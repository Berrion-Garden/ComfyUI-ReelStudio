import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // dev server proxies to a running ComfyUI (or a fake on 8288 for testing)
  server: {
    proxy: {
      "/reelstudio/api": {
        target: process.env.REELSTUDIO_API ?? "http://localhost:8188",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", globals: true },
});
