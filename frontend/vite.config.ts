import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Python API (backend/graphsim/server.py) runs on port 8000; proxy it so the viewer can use
// relative URLs in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
