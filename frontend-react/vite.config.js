import { defineConfig } from "vite";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },

  server: {
    port: 5173,
    host: "127.0.0.1",

    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
