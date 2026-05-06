#!/usr/bin/env node
// M5 codemod: strip <Layout> wrap from pages and add wrapLayout flags to routes.
//
// Usage:
//   node tools/codemod-layout/codemod.mjs inventory     # analyze only, no writes
//   node tools/codemod-layout/codemod.mjs dry-run       # produce .diff per file
//   node tools/codemod-layout/codemod.mjs apply         # write changes
//
// Strategy:
//   - Strict regex-based transform; rejects files not matching expected pattern.
//   - Each page's <Layout ... currentModule="X" ...> opening tags must all share
//     the same currentModule (or all omit it, e.g. ARIPushDashboard).
//   - Removes `import Layout from '@/components/Layout'` line.
//   - Replaces `<Layout ...>` with `<>` and `</Layout>` with `</>` (always-safe).
//   - Updates routeDefinitions.jsx: every `...p(Component)` / `...pa(Component)`
//     / `...pm(Component, ...)` reference of a transformed component receives
//     `, wrapLayout: true, layoutModule: "<value>"` suffix.
//   - Pages with no route entry are SKIPPED (would orphan their Layout).
//   - Pages already migrated (no Layout import) are SKIPPED.

import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";

const REPO = path.resolve(new URL("../..", import.meta.url).pathname);
const PAGES_DIR = path.join(REPO, "frontend/src/pages");
const ROUTE_DEFS = path.join(REPO, "frontend/src/routes/routeDefinitions.jsx");
const REPORT_DIR = path.join(REPO, "tools/codemod-layout/.report");

const MODE = process.argv[2] || "inventory";
if (!["inventory", "dry-run", "apply"].includes(MODE)) {
  console.error(`Unknown mode: ${MODE}`);
  process.exit(2);
}

fs.mkdirSync(REPORT_DIR, { recursive: true });

// ── 1. Walk pages ────────────────────────────────────────────────────
function listPageFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...listPageFiles(full));
    else if (e.name.endsWith(".jsx") || e.name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

const allPages = listPageFiles(PAGES_DIR);

// Component name = basename without ext.
const componentNameOf = (file) => path.basename(file, path.extname(file));

// ── 2. Parse routeDefinitions.jsx to map Component → list of route lines ──
const routesText = fs.readFileSync(ROUTE_DEFS, "utf8");
const routesLines = routesText.split("\n");

// Identify lines like: `{ path: "/x", ...p(ComponentName, ...maybeProps) }, // optional comment`
// or: `{ path: "/x", ...pa(ComponentName) }`
// or: `{ path: "/x", ...pm(ComponentName, "moduleKey", ...) }`
// Capture: line index, component name, whether already has wrapLayout.
const routeLineRe = /\{\s*path:\s*"[^"]+",\s*\.\.\.(?:p|pa|pm)\(\s*([A-Z][A-Za-z0-9_]*)\b/;
const routeIndex = new Map(); // componentName -> [{lineIdx, hasWrapLayout}]
routesLines.forEach((line, idx) => {
  const m = line.match(routeLineRe);
  if (!m) return;
  const comp = m[1];
  const has = /\bwrapLayout\s*:/.test(line);
  if (!routeIndex.has(comp)) routeIndex.set(comp, []);
  routeIndex.get(comp).push({ lineIdx: idx, hasWrapLayout: has });
});

// Components imported via `lazy(() => import("@/pages/Foo"))` — needed to
// confirm the route file actually references this page.
const lazyImportRe = /const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*lazy\(\s*\(\)\s*=>\s*import\(\s*"@\/pages\/([^"]+)"\s*\)/g;
const lazyMap = new Map(); // pagePathFromImport -> exportedConst
for (const m of routesText.matchAll(lazyImportRe)) {
  lazyMap.set(m[2], m[1]);
}

// ── 3. Per-page analysis ─────────────────────────────────────────────
// Layout import patterns we accept (default-import "Layout" only; reject
// `MaybeLayout` and any other distinct symbol). Both `@/components/Layout`
// and the relative `../components/Layout` form are supported.
const importRe =
  /^[ \t]*import\s+Layout\s+from\s+["'](?:@\/components\/Layout|\.\.\/components\/Layout)["'];?\s*$/m;

// Brace-aware <Layout ...> opening tag finder. Naive `<Layout\b([^>]*?)>`
// breaks on attrs containing `>` inside JSX expressions (e.g. arrow fns:
// `onLogout={() => {}}`). We walk char-by-char tracking brace depth and
// string state to find the real closing `>`.
function findLayoutOpens(src) {
  const opens = [];
  const re = /<Layout\b/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    let i = m.index + "<Layout".length;
    let depth = 0;
    let inString = null;
    let found = false;
    while (i < src.length) {
      const c = src[i];
      if (inString) {
        if (c === inString && src[i - 1] !== "\\") inString = null;
      } else if (c === '"' || c === "'" || c === "`") {
        inString = c;
      } else if (c === "{") depth++;
      else if (c === "}") depth--;
      else if (c === ">" && depth === 0) {
        opens.push({
          idx: m.index,
          end: i + 1,
          attrs: src.slice(m.index + "<Layout".length, i),
          full: src.slice(m.index, i + 1),
        });
        found = true;
        break;
      }
      i++;
    }
    if (!found) {
      // Unterminated tag — treat as parse failure for this file.
      opens.push({ idx: m.index, end: -1, attrs: "", full: "<Layout" });
    }
  }
  return opens;
}

const closeTagRe = /<\/Layout\s*>/g;

const reports = [];

for (const file of allPages) {
  const rel = path.relative(REPO, file);
  const src = fs.readFileSync(file, "utf8");

  // Skip files without Layout import.
  if (!importRe.test(src)) continue;

  const importMatch = src.match(importRe);
  const pageComp = componentNameOf(file);

  // Verify the page is referenced via lazy import in routeDefinitions.
  // pagePathFromImport is the relative-from-pages path.
  // Try a few keys: bare name and subdir variants.
  const pageImportKey =
    Array.from(lazyMap.keys()).find(
      (k) => k === pageComp || k.endsWith("/" + pageComp),
    ) || null;
  const lazyComp = pageImportKey ? lazyMap.get(pageImportKey) : null;
  const routeEntries = lazyComp ? routeIndex.get(lazyComp) || [] : [];

  // Collect <Layout ...> opening tags via brace-aware parser.
  const opens = findLayoutOpens(src);
  if (opens.some((o) => o.end === -1)) {
    reports.push({ file: rel, status: "REJECT", reason: "unterminated <Layout tag" });
    continue;
  }
  const closes = [];
  let m;
  closeTagRe.lastIndex = 0;
  while ((m = closeTagRe.exec(src)) !== null) {
    closes.push({ idx: m.index, full: m[0] });
  }

  if (opens.length === 0) {
    reports.push({ file: rel, status: "SKIP", reason: "no <Layout> tag found despite import" });
    continue;
  }
  if (opens.length !== closes.length) {
    reports.push({
      file: rel,
      status: "REJECT",
      reason: `unbalanced tags: opens=${opens.length} closes=${closes.length}`,
    });
    continue;
  }

  // Extract currentModule from each open tag; ensure consistency.
  const cmRe = /\bcurrentModule\s*=\s*"([^"]+)"/;
  const modules = opens.map((o) => {
    const mm = o.attrs.match(cmRe);
    return mm ? mm[1] : null;
  });
  const distinctModules = Array.from(new Set(modules));
  if (distinctModules.length > 1) {
    reports.push({
      file: rel,
      status: "REJECT",
      reason: `multiple distinct currentModule values: ${JSON.stringify(distinctModules)}`,
    });
    continue;
  }
  const currentModule = distinctModules[0]; // may be null (e.g. ARIPushDashboard)

  if (!lazyComp || routeEntries.length === 0) {
    reports.push({
      file: rel,
      status: "SKIP",
      reason: `no route entry references this page (lazyComp=${lazyComp})`,
      currentModule,
    });
    continue;
  }

  reports.push({
    file: rel,
    status: "OK",
    currentModule,
    occurrences: opens.length,
    routeComponent: lazyComp,
    routeLineCount: routeEntries.length,
    routeAlreadyHasWrapLayout: routeEntries.every((r) => r.hasWrapLayout),
  });
}

// ── 4. Report summary ────────────────────────────────────────────────
const ok = reports.filter((r) => r.status === "OK");
const skipped = reports.filter((r) => r.status === "SKIP");
const rejected = reports.filter((r) => r.status === "REJECT");

console.log(`\n=== M5 Codemod Inventory (mode=${MODE}) ===`);
console.log(`OK (will transform):     ${ok.length}`);
console.log(`SKIP (no route or already migrated): ${skipped.length}`);
console.log(`REJECT (manual review needed):       ${rejected.length}`);
console.log(`Total candidates: ${reports.length}\n`);

fs.writeFileSync(
  path.join(REPORT_DIR, "inventory.json"),
  JSON.stringify({ ok, skipped, rejected }, null, 2),
);
console.log(`Inventory: ${path.relative(REPO, path.join(REPORT_DIR, "inventory.json"))}`);

if (rejected.length) {
  console.log("\n--- REJECTED ---");
  for (const r of rejected) console.log(`  ${r.file}: ${r.reason}`);
}
if (skipped.length) {
  console.log("\n--- SKIPPED ---");
  for (const r of skipped.slice(0, 20)) console.log(`  ${r.file}: ${r.reason}`);
  if (skipped.length > 20) console.log(`  ... and ${skipped.length - 20} more`);
}

if (MODE === "inventory") process.exit(rejected.length ? 1 : 0);

// ── 5. Transform pages ───────────────────────────────────────────────
function transformPageSrc(src) {
  // Remove import line (first occurrence; importRe is anchored to a full line).
  let out = src.replace(importRe, "");
  // Drop a single leading blank line if the import was at top.
  out = out.replace(/^\s*\n/, (s) => (s.length > 1 ? "" : s));
  // Replace opening tags via brace-aware parser, RTL so indices stay valid.
  const opens = findLayoutOpens(out);
  for (let k = opens.length - 1; k >= 0; k--) {
    const o = opens[k];
    out = out.slice(0, o.idx) + "<>" + out.slice(o.end);
  }
  // Replace closing tags.
  out = out.replace(closeTagRe, "</>");
  return out;
}

// ── 6. Transform routeDefinitions.jsx ────────────────────────────────
function transformRoutesText(text, transformedComps) {
  const lines = text.split("\n");
  // For each route entry line referencing a transformed component, insert
  // `, wrapLayout: true, layoutModule: "X"` before the trailing `}`.
  // We must find the matching closing `}` of the object literal; since most
  // entries are single-line, use a single-line regex first; for the rare
  // multi-line case we walk forward.
  const compToModule = new Map(transformedComps.map((c) => [c.routeComponent, c.currentModule]));
  let modified = 0;

  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(routeLineRe);
    if (!m) continue;
    const comp = m[1];
    if (!compToModule.has(comp)) continue;
    if (/\bwrapLayout\s*:/.test(lines[i])) continue; // already migrated
    const layoutModule = compToModule.get(comp);
    const flag =
      layoutModule != null
        ? `, wrapLayout: true, layoutModule: "${layoutModule}"`
        : `, wrapLayout: true`;

    // Find the closing `}` of THIS object on this line. The standard pattern is:
    //   { path: "/x", ...p(Component) },
    // We insert `flag` immediately before the matching `}`.
    // Use last `}` on the line that is followed by an optional `,` and end (or comment).
    const closeRe = /\}(\s*,?\s*(?:\/\/.*)?)$/;
    if (closeRe.test(lines[i])) {
      lines[i] = lines[i].replace(closeRe, `${flag} }$1`);
      modified++;
    } else {
      // Multi-line entry: walk forward to find first standalone `}`.
      let j = i + 1;
      while (j < lines.length && !/^\s*\}/.test(lines[j])) j++;
      if (j < lines.length) {
        lines[j] = lines[j].replace(/^(\s*)\}/, `$1${flag.replace(/^,\s*/, "")}, }`);
        modified++;
      }
    }
  }
  return { text: lines.join("\n"), modified };
}

// ── 7. Diff helper ───────────────────────────────────────────────────
function diff(filePath, before, after) {
  if (before === after) return "";
  const b = path.join(REPORT_DIR, "_b_" + path.basename(filePath));
  const a = path.join(REPORT_DIR, "_a_" + path.basename(filePath));
  fs.writeFileSync(b, before);
  fs.writeFileSync(a, after);
  try {
    return execSync(`diff -u "${b}" "${a}" || true`, { encoding: "utf8" });
  } finally {
    fs.unlinkSync(b);
    fs.unlinkSync(a);
  }
}

// ── 8. Execute ───────────────────────────────────────────────────────
const diffs = [];
const writes = [];

for (const r of ok) {
  const abs = path.join(REPO, r.file);
  const src = fs.readFileSync(abs, "utf8");
  const next = transformPageSrc(src);
  if (next === src) continue;
  diffs.push({ file: r.file, diff: diff(abs, src, next) });
  writes.push({ abs, content: next });
}

const routesBefore = fs.readFileSync(ROUTE_DEFS, "utf8");
const { text: routesAfter, modified: routesModified } = transformRoutesText(routesBefore, ok);
if (routesAfter !== routesBefore) {
  diffs.push({ file: path.relative(REPO, ROUTE_DEFS), diff: diff(ROUTE_DEFS, routesBefore, routesAfter) });
  writes.push({ abs: ROUTE_DEFS, content: routesAfter });
}

console.log(`\nPage diffs: ${diffs.length - (routesAfter !== routesBefore ? 1 : 0)}`);
console.log(`Route lines modified: ${routesModified}`);

const diffPath = path.join(REPORT_DIR, "changes.diff");
fs.writeFileSync(diffPath, diffs.map((d) => `\n# ${d.file}\n${d.diff}`).join("\n"));
console.log(`Diff: ${path.relative(REPO, diffPath)}`);

if (MODE === "dry-run") {
  console.log("\nDry-run complete. Review .report/changes.diff then re-run with `apply`.");
  process.exit(0);
}

// APPLY
for (const w of writes) fs.writeFileSync(w.abs, w.content);
console.log(`\n✅ Applied ${writes.length} file writes.`);
