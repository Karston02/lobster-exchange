import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, forward API and websocket requests to the Python server.
// LOBSTER_PORT matches the server's setting (see .env.example).
const api = `127.0.0.1:${process.env.LOBSTER_PORT ?? "8000"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": `http://${api}`,
      "/ws": { target: `ws://${api}`, ws: true },
    },
  },
});
