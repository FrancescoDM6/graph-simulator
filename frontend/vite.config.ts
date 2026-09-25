import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Python server (backend/graphsim/server.py) runs on port 8000; proxy its routes so the
// viewer can use relative URLs in development.
const BACKEND = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": BACKEND,
      "/ws": { target: BACKEND, ws: true },
    },
  },
});
