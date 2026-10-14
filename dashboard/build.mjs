// Build dist/cld-reducer-dashboard.html: one self-contained file with the page,
// the solver worker, highs.wasm (gzip-compressed, base64-encoded), the example
// data, the Aigora fonts and mark, the icon, and the license texts. Also build
// dist/site, the directory for a web host: the same page as index.html, with
// the icons and the link preview image from site/.
// Run `npm ci` in ../js first: the solver comes from ../js/src and its
// `highs` dependency from ../js/node_modules.

import { build, transform } from "esbuild";
import { copyFileSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const src = join(here, "src");
const site = join(here, "site");
const brand = join(src, "brand");
const out = join(here, "dist", "cld-reducer-dashboard.html");
const hosted = join(here, "dist", "site");
const requireFromJs = createRequire(join(root, "js", "package.json"));

let wasmPath;
try {
  wasmPath = requireFromJs.resolve("highs/runtime");
} catch {
  console.error("highs is not installed. Run `npm ci` in ../js first.");
  process.exit(1);
}
const read = (...path) => readFileSync(join(...path), "utf8");

const common = { bundle: true, platform: "browser", target: "es2022", minify: true, legalComments: "none" };

// The worker is a classic script, not a module: Chrome does not start a
// module worker from a page opened as a file. The highs loader reads
// import.meta and imports node:* modules only on Node.js.
const worker = await build({
  ...common,
  entryPoints: [join(src, "worker.ts")],
  format: "iife",
  external: ["node:*"],
  logOverride: { "empty-import-meta": "silent" },
  write: false,
});
const workerSource = worker.outputFiles[0].text;

const wasmBase64 = gzipSync(readFileSync(wasmPath), { level: 9 }).toString("base64");

// The version of the JavaScript package, and the example files of the
// conformance suite. Line ends become LF, as a text field holds them.
const version = JSON.parse(read(root, "js", "package.json")).version;
const examples = Object.fromEntries(
  ["simple_abc_to_ac_pairs.csv", "simple_abc_to_ac_means.csv", "piepho2004_wheat_pairs.csv"]
    .map((name) => [name, read(root, "conformance", "data", name).replace(/\r\n/g, "\n")]));

const virtual = {
  name: "virtual",
  setup(b) {
    b.onResolve({ filter: /^virtual:/ }, (args) => ({ path: args.path, namespace: "virtual" }));
    b.onLoad({ filter: /.*/, namespace: "virtual" }, (args) => {
      const module = { "virtual:highs-wasm": wasmBase64, "virtual:worker-source": workerSource,
                       "virtual:repository": { version, examples } }[args.path];
      return module === undefined ? null : { contents: `export default ${JSON.stringify(module)};`, loader: "js" };
    });
  },
};

const app = await build({
  ...common,
  entryPoints: [join(src, "app.ts")],
  format: "esm",
  plugins: [virtual],
  write: false,
});
// "</script" inside the inlined code would end the script element.
const script = app.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");

// The Aigora fonts go into the page as data URLs, so the page works offline.
const font = (file) => `url(data:font/woff2;base64,${readFileSync(join(brand, file)).toString("base64")}) format("woff2")`;
const fontFaces =
  `@font-face{font-family:"Manrope";src:${font("Manrope-Regular.woff2")};font-weight:100 800;font-display:swap}` +
  `@font-face{font-family:"Instrument Serif";src:${font("InstrumentSerif-Italic.woff2")};font-weight:400;font-style:italic;font-display:swap}`;
const css = fontFaces + (await transform(read(src, "styles.css"), { loader: "css", minify: true })).code;

// The icon and the Aigora mark go into the page as data URLs, so that the file needs no other file.
const svgUrl = (path) => "data:image/svg+xml," + readFileSync(path, "utf8")
  .trim().replace(/>\s+</g, "><").replace(/"/g, "'").replace(/[%#<>]/g, encodeURIComponent);
const fontLicense = (file) => read(brand, file).trim();

const escapeHtml = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const parts = {
  "{{version}}": escapeHtml(version),
  "{{license}}": escapeHtml(read(root, "js", "LICENSE").trim()),
  "{{highs-license}}": escapeHtml(read(dirname(dirname(wasmPath)), "LICENSE").trim()),
  "{{notice}}": escapeHtml(read(root, "js", "NOTICE").trim()),
  "{{manrope-license}}": escapeHtml(fontLicense("Manrope-OFL.txt")),
  "{{instrument-license}}": escapeHtml(fontLicense("InstrumentSerif-OFL.txt")),
  "{{favicon}}": svgUrl(join(site, "favicon.svg")),
  "{{logo}}": svgUrl(join(brand, "aigora-mark-light.svg")),
  "/* styles */": css.trim(),
  "/* script */": script.trim(),
};
// One pass, so that inserted text is never read as a placeholder.
const used = new Set();
const page = read(src, "index.html").replace(/\{\{[\w-]+\}\}|\/\* (?:styles|script) \*\//g, (placeholder) => {
  if (!(placeholder in parts)) throw new Error(`index.html has the unknown placeholder ${placeholder}.`);
  used.add(placeholder);
  return parts[placeholder];
});
for (const placeholder of Object.keys(parts)) {
  if (!used.has(placeholder)) throw new Error(`index.html is missing ${placeholder}.`);
}

mkdirSync(hosted, { recursive: true });
writeFileSync(out, page);
writeFileSync(join(hosted, "index.html"), page);
for (const name of ["og.png", "apple-touch-icon.png", "favicon.ico"]) copyFileSync(join(site, name), join(hosted, name));
console.log(`${out} (${(statSync(out).size / 1024 / 1024).toFixed(2)} MB)`);
console.log(hosted);
