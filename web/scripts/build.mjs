/* Build: bundle TS + CSS with esbuild, copy the self-hosted woff2 fonts. */
import { build, context } from "esbuild";
import { globSync, cpSync, mkdirSync, rmSync } from "node:fs";
import { basename, join } from "node:path";

const watch = process.argv.includes("--watch");
const outdir = join(import.meta.dirname, "..", "static", "dist");

const common = {
  entryPoints: ["src/main.ts"],
  bundle: true,
  entryNames: "app",
  outdir,
  sourcemap: true,
  logLevel: "info",
  external: ["/static/*"],
};

function copyFonts() {
  rmSync(join(outdir, "fonts"), { recursive: true, force: true });
  mkdirSync(join(outdir, "fonts"), { recursive: true });
  const stems = [
    "ibm-plex-sans-latin-400-normal",
    "ibm-plex-sans-latin-500-normal",
    "ibm-plex-sans-latin-700-normal",
    "ibm-plex-mono-latin-400-normal",
    "ibm-plex-mono-latin-600-normal",
    "newsreader-latin-400-normal",
    "newsreader-latin-600-normal",
    "newsreader-latin-700-normal",
    "newsreader-latin-400-italic",
    "newsreader-latin-600-italic",
  ];
  for (const stem of stems) {
    const src = globSync(`node_modules/@fontsource/*/files/${stem}.woff2`)[0];
    if (src) cpSync(src, join(outdir, "fonts", basename(src)));
  }
}

if (watch) {
  const ctx = await context(common);
  await copyFonts();
  await ctx.watch();
  console.log("watching…");
} else {
  await build(common);
  await copyFonts();
}