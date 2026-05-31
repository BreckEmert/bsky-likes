import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static SPA. No backend. `npm run build` -> dist/.
export default defineConfig({
  plugins: [react()],
});
