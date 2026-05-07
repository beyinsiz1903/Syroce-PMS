#!/usr/bin/env node
/**
 * Layout regression guard.
 *
 * Fails (exit 1) if any route in `frontend/src/routes/routeDefinitions.jsx`
 * with `wrapLayout: true` points to a page file that still imports the real
 * `Layout` component. This prevents the double-wrap class of bug introduced
 * by partial M5 migrations (route owns Layout, page must NOT also wrap it).
 *
 * What is allowed:
 *  - `import { MaybeLayout }` — conditional embed helper
 *  - `import LayoutSomething` (different name)
 *  - Pages NOT referenced from a wrapLayout:true route
 *
 * What is rejected:
 *  - `import Layout from ...` in a page that a wrapLayout:true route renders
 *
 * Usage: `node frontend/tools/codemod-layout/guard.mjs`
 *        or `cd frontend && yarn guard:layout`
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(__dirname, "../..");
const ROUTE_DEF_PATH = resolve(FRONTEND_ROOT, "src/routes/routeDefinitions.jsx");

if (!existsSync(ROUTE_DEF_PATH)) {
  console.error(`[guard:layout] routeDefinitions not found at ${ROUTE_DEF_PATH}`);
  process.exit(2);
}

const src = readFileSync(ROUTE_DEF_PATH, "utf8");

/* --- 1) Build identifier -> source path map from top-of-file imports --- */
const importMap = new Map();
const importRe = /import\s+(?:\{([^}]+)\}|(\w+))(?:\s*,\s*\{([^}]+)\})?\s+from\s+["']([^"']+)["']/g;
let m;
while ((m = importRe.exec(src)) !== null) {
  const [, namedA, defaultName, namedB, source] = m;
  if (defaultName) importMap.set(defaultName, source);
  for (const block of [namedA, namedB]) {
    if (!block) continue;
    for (const part of block.split(",")) {
      const cleaned = part.trim().split(/\s+as\s+/)[0].trim();
      if (cleaned) importMap.set(cleaned, source);
    }
  }
}

/* --- 2) Find route entries with wrapLayout: true and capture component identifiers --- */
const wrapped = new Set();
const lines = src.split("\n");
for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  if (!line.includes("wrapLayout: true")) continue;
  // Look for component: X or p(X, ...) / pm(X, ...) / pa(X, ...) on the same line
  const match =
    line.match(/component:\s*(\w+)/) ||
    line.match(/\bp[am]?\s*\(\s*(\w+)/) ||
    line.match(/\.\.\.p[am]?\s*\(\s*(\w+)/);
  if (match) {
    wrapped.add(match[1]);
  }
}

/* --- 3) For each wrapped component, resolve its file and check imports --- */
const violations = [];
for (const ident of wrapped) {
  const importPath = importMap.get(ident);
  if (!importPath) continue;
  if (!importPath.startsWith("@/") && !importPath.startsWith("./") && !importPath.startsWith("../")) {
    continue; // 3rd-party
  }

  // Resolve to filesystem path
  const relPath = importPath.startsWith("@/")
    ? resolve(FRONTEND_ROOT, "src", importPath.slice(2))
    : resolve(dirname(ROUTE_DEF_PATH), importPath);

  const candidates = [
    relPath,
    `${relPath}.jsx`,
    `${relPath}.js`,
    `${relPath}.tsx`,
    `${relPath}.ts`,
    `${relPath}/index.jsx`,
    `${relPath}/index.js`,
  ];
  const filePath = candidates.find((p) => existsSync(p));
  if (!filePath) continue;

  const body = readFileSync(filePath, "utf8");
  // Match `import Layout from ...` (default import — the real Layout)
  // Allow `import { MaybeLayout }` and `import LayoutSomething` (different identifier).
  if (/^\s*import\s+Layout\s+from\s+/m.test(body)) {
    violations.push({ ident, filePath: filePath.replace(FRONTEND_ROOT + "/", "") });
  }
}

if (violations.length === 0) {
  console.log(`[guard:layout] OK — ${wrapped.size} wrapLayout routes clean.`);
  process.exit(0);
}

console.error(`[guard:layout] ${violations.length} violation(s):`);
for (const v of violations) {
  console.error(`  - ${v.ident} (${v.filePath}) imports Layout but route uses wrapLayout: true`);
}
console.error("");
console.error("Fix: remove `import Layout` and the <Layout> wrapper from the page.");
console.error("Routes wrap with Layout via routeDefinitions.jsx — pages must return content only.");
process.exit(1);
