import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In development, forward API and websocket requests to the Python server.
// The port comes from LOBSTER_PORT, read like the server reads it: the real
// environment first, then the .env at the repo root. Only LOBSTER_* values
// are loaded, and none of them reach the browser bundle.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../..", "LOBSTER_"); // npm runs this from dashboard/web
  const api = `127.0.0.1:${env.LOBSTER_PORT || "8000"}`;
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": `http://${api}`,
        "/ws": { target: `ws://${api}`, ws: true },
      },
    },
  };
});
