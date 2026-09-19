import { build } from "esbuild";
import { rmSync } from "node:fs";
rmSync("../site/privy", { recursive: true, force: true });
const result = await build({
  entryPoints: ["entry.jsx"],
  bundle: true,
  minify: true,
  splitting: true,
  format: "esm",
  target: ["es2020"],
  outdir: "../site/privy",
  entryNames: "privy",
  chunkNames: "c-[hash]",
  define: { "process.env.NODE_ENV": '"production"', global: "window" },
  jsx: "automatic",
  legalComments: "none",
  logLevel: "warning",
  metafile: true,
});
