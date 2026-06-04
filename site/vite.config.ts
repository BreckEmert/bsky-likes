import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static SPA. No backend. `npm run build` -> dist/.
// base: root by default; set VITE_BASE="/bsky-likes-analysis/" (or your repo
// name) when deploying to a GitHub *project* page. Runtime asset fetches go
// through src/lib/asset.ts, which honors this base.
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
});
