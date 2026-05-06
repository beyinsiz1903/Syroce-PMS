#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const ROUTE_FILE = path.join(REPO_ROOT, "frontend/src/routes/routeDefinitions.jsx");
const PAGES_DIR = path.join(REPO_ROOT, "frontend/src/pages");

function resolvePagePath(importSpec) {
  let rel = importSpec;
  if (rel.startsWith("@/")) rel = rel.slice(2);
  else if (rel.startsWith("./") || rel.startsWith("../")) {
    rel = path.relative(
      path.join(REPO_ROOT, "frontend/src"),
      path.resolve(path.dirname(ROUTE_FILE), rel),
    );
  }
  for (const ext of [".jsx", ".js", ".tsx", ".ts"]) {
    const full = path.join(REPO_ROOT, "frontend/src", rel + ext);
    if (fs.existsSync(full)) return full;
  }
  return null;
}

function main() {
  if (!fs.existsSync(ROUTE_FILE)) {
    console.error(`[guard] Route file not found: ${ROUTE_FILE}`);
    process.exit(2);
  }

  const src = fs.readFileSync(ROUTE_FILE, "utf8");

  const lazyMap = new Map();
  const lazyRe = /^const\s+(\w+)\s*=\s*lazy\(\s*\(\)\s*=>\s*import\(\s*["']([^"']+)["']\s*\)\s*\)\s*;/gm;
  for (const m of src.matchAll(lazyRe)) {
    const [, name, spec] = m;
    const filePath = resolvePagePath(spec);
    if (filePath) lazyMap.set(name, filePath);
  }

  const violations = [];
  const warnings = [];
  const lines = src.split("\n");
  lines.forEach((line, idx) => {
    if (!/wrapLayout\s*:\s*true/.test(line)) return;
    if (/^\s*\/\//.test(line)) return;
    const callMatch = line.match(/\b(?:p|pm|pf|pa|pp)\s*\(\s*(\w+)/);
    if (!callMatch) {
      warnings.push({ line: idx + 1, content: line.trim(), reason: "wrapLayout: true present but component name could not be parsed" });
      return;
    }
    const compName = callMatch[1];
    const filePath = lazyMap.get(compName);
    if (!filePath) {
      warnings.push({ line: idx + 1, component: compName, reason: "lazy import not found in route file" });
      return;
    }
    const pageSrc = fs.readFileSync(filePath, "utf8");
    const hasLayoutImport = /^\s*import\s+Layout\s+from\s+["'](?:@\/components\/Layout|\.\.\/components\/Layout)["'];?/m.test(pageSrc);
    if (hasLayoutImport) {
      const hasJsxUse = /<Layout[\s/>]/.test(pageSrc);
      violations.push({
        line: idx + 1,
        component: compName,
        file: path.relative(REPO_ROOT, filePath),
        kind: hasJsxUse ? "double-wrap (Layout still rendered)" : "stale import (no JSX use)",
      });
    }
  });

  if (warnings.length) {
    console.warn(`\n[guard] ${warnings.length} warning(s):`);
    for (const w of warnings) console.warn(`  - L${w.line} ${w.component ?? ""} — ${w.reason}`);
  }

  if (violations.length === 0) {
    console.log(`[guard] OK — no double-wrap regressions detected (scanned ${lazyMap.size} lazy imports).`);
    process.exit(0);
  }

  console.error(`\n[guard] FAIL — ${violations.length} double-wrap regression(s) detected:\n`);
  for (const v of violations) {
    console.error(`  • ${v.component} (route L${v.line})`);
    console.error(`      file:   ${v.file}`);
    console.error(`      reason: ${v.kind}`);
    console.error(`      fix:    remove "import Layout" + "<Layout>" wrap from the page (route owns the layout)`);
    console.error("");
  }
  console.error("See replit.md → 'Pages Layout Wrap' gotcha for the migration pattern.\n");
  process.exit(1);
}

main();
