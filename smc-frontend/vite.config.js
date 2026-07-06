import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API = "http://127.0.0.1:5000";

/** Let React Router handle page loads; only proxy XHR/fetch to Flask. */
function spaBypass(req) {
  const accept = req.headers.accept || "";
  if (req.method === "GET" && accept.includes("text/html")) {
    return req.url;
  }
}

function apiProxy(paths) {
  return Object.fromEntries(
    paths.map((path) => [path, { target: API, changeOrigin: true, bypass: spaBypass }])
  );
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  base: mode === "production" ? "/app/" : "/",
  appType: "spa",
  build: {
    outDir: "../static/app",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      ...apiProxy([
        "/login",
        "/logout",
        "/refresh",
        "/register",
        "/forgot-password",
        "/reset-password",
        "/me",
        "/my",
        "/analyze",
        "/calculator",
        "/pairs",
        "/notifications",
        "/telegram",
        "/healthz",
      ]),
      // SSE trade stream only — not a React page route
      "^/predict/\\d+": { target: API, changeOrigin: true },
    },
  },
}));
