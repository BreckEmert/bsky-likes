// Resolve a public-asset path against Vite's base URL, so the site works served
// from the domain root ("/") OR a sub-path ("/bsky-likes-analysis/"). Use this
// for every RUNTIME fetch of something in public/ (bundled JS/CSS already get
// the base from Vite automatically).
export function asset(path: string | null | undefined): string {
  if (!path) return path as string;
  return import.meta.env.BASE_URL + path.replace(/^\//, "");
}
