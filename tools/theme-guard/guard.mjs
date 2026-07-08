#!/usr/bin/env node
/**
 * Dark-coverage + brand-drift regression guard (Faz 4).
 *
 * Two independent gates, both must pass (exit 1 on any failure):
 *
 *  (A) DARK COVERAGE — every neutral/pastel color utility ACTUALLY USED in
 *      frontend/src JSX must have a matching `.dark` compat rule in
 *      frontend/src/index.css, UNLESS it is a documented skip (solid button,
 *      glass overlay, mid-shade indicator, light-text tint, responsive/dark
 *      prefixed, out-of-scope property), lives only on an always-dark-by-design
 *      page, or is explicitly allow-listed below. A new uncovered genuine gap
 *      (= a JSX color that would flash bright in dark mode) FAILS the guard.
 *
 *  (B) BRAND DRIFT — purple/orange are retired brand hues (purple->indigo,
 *      orange->amber). They are allowed ONLY inside index.css (the preserved,
 *      dead-safe compat snapshot). Any purple/orange color utility in a JSX/TSX
 *      component FAILS the guard.
 *
 * Doctrine: this guard NEVER loosens an assertion. To clear a real new gap,
 * add an additive `.dark` rule (hue + alpha preserving) to index.css — do not
 * widen the skip rules. To intentionally exempt a token, add it to an allowlist
 * below WITH a one-line justification.
 *
 * Usage: `node tools/theme-guard/guard.mjs`  or  `cd frontend && yarn guard:theme`
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, resolve, join, relative, basename } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(__dirname, "../../frontend");
const SRC = resolve(FRONTEND_ROOT, "src");
const CSS = resolve(SRC, "index.css");

if (!existsSync(CSS)) {
  console.error(`[guard:theme] index.css not found at ${CSS}`);
  process.exit(2);
}

/* ---- Tailwind vocabulary ---- */
const FAM = ["slate","gray","zinc","neutral","stone","red","orange","amber","yellow","lime","green","emerald","teal","cyan","sky","blue","indigo","violet","purple","fuchsia","pink","rose"];
const PROP = ["text","bg","border","ring","ring-offset","from","via","to","divide","placeholder","fill","stroke","outline","decoration","caret","accent","shadow"];
const SHADE = ["50","100","200","300","400","500","600","700","800","900","950"];
const NEUTRAL = new Set(["slate","gray","zinc","neutral","stone"]);
const RESPONSIVE = new Set(["sm","md","lg","xl","2xl"]);

/* ---- Allowlists (each entry needs a justification) ---- */
// Pages whose root is dark-by-design (hardcoded bg-[#05070f] + text-slate-100);
// the .dark compat layer need not apply — no blind spot regardless of theme.
const ALWAYS_DARK = new Set(["LandingPage.jsx", "AuthPage.jsx", "SupplierAuthPage.jsx"]);
// Tokens deliberately left uncovered, BOUND to the specific file(s) where the
// exemption is valid. A token is exempt ONLY when EVERY file it appears in is in
// `files` — a future use of the same utility on any OTHER (theme-responsive)
// page is NOT silently allowed and will FAIL the guard (architect-hardened).
// NB: NightScreen's dim clock uses arbitrary `text-[#525252]/[#404040]` to escape
// the compat, so it produces no neutral utility token here and needs no entry.
const INTENTIONAL_UNCOVERED = [
  {
    token: "hover:to-teal-200",
    files: new Set(["pages/AuthPage.jsx"]),
    // AuthPage is already dark-by-design (ALWAYS_DARK); this is a defensive
    // double-lock for its bright dark-text CTA gradient.
    why: "AuthPage primary-CTA gradient w/ explicit dark text — bright CTA by design",
  },
];

function walk(dir, acc) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) { if (e.name === "node_modules") continue; walk(p, acc); }
    else if (/\.(jsx?|tsx?)$/.test(e.name)) acc.push(p);
  }
  return acc;
}

const propAlt = PROP.slice().sort((a, b) => b.length - a.length).join("|");
const famAlt = FAM.join("|");
const shadeAlt = SHADE.slice().sort((a, b) => b.length - a.length || Number(b) - Number(a)).join("|");
const TOKEN = new RegExp(
  "((?:(?:[a-z0-9-]+(?:-\\[[^\\]]+\\])?|data-\\[[^\\]]+\\]|aria-\\[[^\\]]+\\]):)*)" +
  "(" + propAlt + ")-(" + famAlt + ")-(" + shadeAlt + ")(?![0-9])" +
  "(\\/(?:\\d{1,3}))?(?![0-9])",
  "g"
);

function enclosingCtx(txt, idx) {
  const opener = Math.max(txt.lastIndexOf('"', idx), txt.lastIndexOf("'", idx), txt.lastIndexOf("`", idx));
  if (opener >= 0) {
    const ch = txt[opener];
    let close = txt.indexOf(ch, idx);
    if (close < 0) close = idx + 200;
    if (close - opener > 1400) return txt.slice(Math.max(0, idx - 250), idx + 250);
    return txt.slice(opener, close + 1);
  }
  return txt.slice(Math.max(0, idx - 250), idx + 250);
}

// An element already carrying a dark: override of the SAME property is not a blind spot.
function inlineDarkCovered(prop, ctx) {
  if (prop === "from" || prop === "via" || prop === "to") return /dark:bg-none/.test(ctx) || /dark:(from|via|to)-/.test(ctx);
  if (prop === "bg") return /dark:bg-/.test(ctx);
  if (prop === "text") return /dark:text-/.test(ctx);
  if (prop === "border") return /dark:border-/.test(ctx);
  if (prop === "divide") return /dark:divide-/.test(ctx);
  if (prop === "placeholder") return /dark:placeholder/.test(ctx);
  return false;
}

function classify(variants, prop, fam, shade, op) {
  const vlist = variants.filter(Boolean);
  if (vlist.some((v) => RESPONSIVE.has(v) || v === "dark" || v === "print")) return null;
  const canon = (vlist.length ? vlist.join(":") + ":" : "") + `${prop}-${fam}-${shade}` + (op || "");
  return canon;
}

// Skip doctrine (mirrors the audit): tokens that are correct as-is in dark mode.
function skipReason(prop, fam, shade, op) {
  const isNeutral = NEUTRAL.has(fam);
  if (prop === "text" && shade <= 300) return "LIGHT_TEXT";
  if (op) { const opv = parseInt(op.slice(1), 10); if (isNeutral && opv < 50) return "GLASS"; }
  if (isNeutral && (prop === "bg" || prop === "border") && shade >= 300) return "NEUTRAL_MIDSHADE";
  if (!isNeutral && prop === "bg" && shade >= 300) return "SOLID_PASTEL";
  if ((prop === "from" || prop === "via" || prop === "to") && shade >= 300) return "GRADIENT_SATURATED";
  if (!isNeutral && prop === "border" && shade >= 400) return "SOLID_BORDER";
  if (["ring", "fill", "stroke", "shadow", "outline", "decoration", "caret", "accent", "ring-offset"].includes(prop)) return "PROP_OOS";
  return null;
}

function parseCanon(canon) {
  const m = canon.match(/^(.*?:)?((?:text|bg|border|ring|ring-offset|from|via|to|divide|placeholder|fill|stroke|outline|decoration|caret|accent|shadow))-([a-z]+)-(\d+)(\/\d+)?$/);
  if (!m) return null;
  return { prop: m[2], fam: m[3], shade: parseInt(m[4], 10), op: m[5] || "" };
}

/* ---- Scan JSX: USED tokens (with live/inline-dark/always-dark split) + purple/orange usage ---- */
const files = walk(SRC, []);
const tok = new Map(); // canon -> { live, brandDrift list }
const brand = []; // { file, token }
const BRAND_RE = new RegExp(
  "(?:[a-z0-9-]+(?:-\\[[^\\]]+\\])?:)*(?:" + propAlt + ")-(?:purple|orange)-(?:" + shadeAlt + ")(?![0-9])(?:\\/\\d{1,3})?",
  "g"
);

for (const f of files) {
  const rel = relative(SRC, f);
  const base = basename(f);
  const txt = readFileSync(f, "utf8");

  // (B) brand drift — any purple/orange utility in a component
  let bm; BRAND_RE.lastIndex = 0;
  while ((bm = BRAND_RE.exec(txt)) !== null) brand.push({ file: rel, token: bm[0] });

  // (A) dark coverage — collect live (theme-responsive, not inline-dark) occurrences
  let m; TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(txt)) !== null) {
    const pre = m[1] || "";
    const variants = pre.split(":").map((s) => s.trim()).filter(Boolean);
    const prop = m[2], fam = m[3], shade = m[4], op = m[5] || "";
    // Reject impossible Tailwind opacities (>100): these never occur in real
    // classNames and only appear in prose/comments (e.g. NightScreen's
    // "text-neutral-600/700 -> ..." explainer), so they are false positives.
    if (op && parseInt(op.slice(1), 10) > 100) continue;
    const canon = classify(variants, prop, fam, shade, op);
    if (!canon) continue;
    const ctx = enclosingCtx(txt, m.index);
    if (inlineDarkCovered(prop, ctx)) continue;
    if (ALWAYS_DARK.has(base)) continue;
    if (!tok.has(canon)) tok.set(canon, { live: 0, files: new Set() });
    const t = tok.get(canon);
    t.live++; t.files.add(rel);
  }
}

/* ---- COVERED set from index.css `.dark` selectors ---- */
const css = readFileSync(CSS, "utf8");
const covered = new Set();
const selRe = /\.dark[^,{}]*/g;
let sm;
while ((sm = selRe.exec(css)) !== null) {
  let s = sm[0].trim();
  s = s.replace(/\s*>\s*:not\(\[hidden\]\)\s*~\s*:not\(\[hidden\]\)\s*$/, "");
  s = s.replace(/\.dark\s+/g, "");
  s = s.replace(/\.group:hover\s+/g, "");
  s = s.trim();
  s = s.replace(/\[data-state=active\]$/, "");
  s = s.replace(/::placeholder$/, "");
  let prev;
  do {
    prev = s;
    s = s.replace(/:hover$|:disabled$|:focus$|:checked$|:active$/, "");
  } while (s !== prev);
  s = s.trim().replace(/^\./, "");
  s = s.replace(/\\/g, "");
  if (s) covered.add(s);
}

/* ---- Compute genuine uncovered gaps ---- */
const gaps = [];
for (const [canon, t] of tok) {
  if (t.live <= 0) continue;
  if (covered.has(canon)) continue;
  // File-bound exemption: only skip when EVERY occurrence file is allow-listed
  // for this exact token (a future use elsewhere is NOT silently exempted).
  const exempt = INTENTIONAL_UNCOVERED.find((e) => e.token === canon);
  if (exempt && [...t.files].every((f) => exempt.files.has(f))) continue;
  const p = parseCanon(canon);
  if (!p) continue;
  if (skipReason(p.prop, p.fam, p.shade, p.op)) continue;
  gaps.push({ canon, n: t.live, files: [...t.files] });
}
gaps.sort((a, b) => b.n - a.n);

/* ---- Report ---- */
let failed = false;

if (gaps.length > 0) {
  failed = true;
  console.error(`[guard:theme] (A) DARK COVERAGE — ${gaps.length} new uncovered gap(s):`);
  for (const g of gaps) {
    console.error(`  - ${g.canon}  (x${g.n})  e.g. ${g.files.slice(0, 3).join(", ")}`);
  }
  console.error("  Fix: add an additive `.dark` rule (hue + alpha preserving) to frontend/src/index.css.");
  console.error("  Do NOT widen the skip doctrine. If truly dark-by-design, allow-list with justification.\n");
}

if (brand.length > 0) {
  failed = true;
  const byTok = new Map();
  for (const b of brand) {
    if (!byTok.has(b.token)) byTok.set(b.token, new Set());
    byTok.get(b.token).add(b.file);
  }
  console.error(`[guard:theme] (B) BRAND DRIFT — ${brand.length} purple/orange usage(s) in components:`);
  for (const [t, fs2] of byTok) {
    console.error(`  - ${t}  e.g. ${[...fs2].slice(0, 3).join(", ")}`);
  }
  console.error("  Fix: purple->indigo, orange->amber. These hues are retired (allowed only in index.css compat).\n");
}

if (failed) process.exit(1);

console.log(
  `[guard:theme] OK — ${files.length} files scanned; ` +
  `${tok.size} live color utilities, all covered/skip/allow-listed; ` +
  `0 brand-drift (purple/orange) component usages.`
);
process.exit(0);
