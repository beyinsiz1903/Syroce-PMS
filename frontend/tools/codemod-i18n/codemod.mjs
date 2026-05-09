#!/usr/bin/env node
/**
 * i18n codemod — converts hardcoded TR strings in JSX to t('key') calls.
 *
 * Surgical splice mode: parses with @babel/parser to locate strings,
 * then performs byte-offset string replacements so the rest of the file
 * (formatting, comments, blank lines, quote style) is preserved.
 *
 * Modes:
 *   --dry        Print plan, no writes (default)
 *   --apply      Write transformed files + locale JSON updates
 *   --limit=N    Process at most N files (debugging)
 *   --preview    Print transformed source of the first processed file
 *   --files=…    Comma-separated relative paths (default: full sweep)
 *
 * Output:
 *   tools/codemod-i18n/report.json — per-file outcome
 *   tools/codemod-i18n/keys.json   — newly generated key → TR value map
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import crypto from 'node:crypto';
import * as parser from '@babel/parser';
import _traverse from '@babel/traverse';
import * as t from '@babel/types';

const traverse = _traverse.default || _traverse;

const __filename = fileURLToPath(import.meta.url);
const ROOT = resolve(dirname(__filename), '../..'); // frontend/
const SRC = resolve(ROOT, 'src');
const LOCALES = resolve(SRC, 'locales');
const REPORT_DIR = resolve(ROOT, 'tools/codemod-i18n');

const args = Object.fromEntries(
  process.argv.slice(2).map(a => {
    const [k, v] = a.replace(/^--/, '').split('=');
    return [k, v ?? true];
  })
);
const APPLY = !!args.apply;
const LIMIT = args.limit ? parseInt(args.limit, 10) : Infinity;
const PREVIEW = !!args.preview;
const FILES_ARG = args.files ? String(args.files).split(',') : null;

// ── TR detection heuristics ──────────────────────────────────────────────────
const TR_CHAR_RE = /[ÇĞİÖŞÜçğıöşü]/;
const TR_WORD_RE = /\b(Rezervasyon|Misafir|Oda|Yenile|Kaydet|İptal|Iptal|Ekle|Sil|Düzenle|Duzenle|Yükleniyor|Yukleniyor|Hata|Başarılı|Basarili|Tamam|Evet|Hayır|Hayir|Giriş|Cikis|Çıkış|Konuk|Kişi|Kisi|Tarih|Saat|Toplam|Bakiye|Ödeme|Odeme|Tutar|Açıklama|Aciklama|Durum|Aktif|Pasif|Yeni|Eski|Bugün|Bugun|Dün|Dun|Yarın|Yarin|Hafta|Ay|Yıl|Yil|Saat|Dakika|Saniye|Liste|Tablo|Filtre|Ara|Bul|Göster|Goster|Gizle|Aç|Ac|Kapat|Onayla|Reddet|Sil|Yükle|Yukle|İndir|Indir|Yazdır|Yazdir|Paylaş|Paylas|Gönder|Gonder|Aldı|Aldi|Verdi|Boş|Bos|Dolu|Temiz|Kirli|Hazır|Hazir|Beklemede|Tamamlandı|Tamamlandi|Onaylandı|Onaylandi|Adı|Adi|Soyadı|Soyadi|Numarası|Numarasi|Türü|Turu|Sayısı|Sayisi)\b/;
const SKIP_RE = /^[\s\d.,:/\-_=()[\]{}<>+*&%$#@!?'"`~|\\]*$/;
const URL_RE = /^(https?:|\/api\/|\/[a-z]+\/|mailto:|tel:|#|\?)/i;
const CODE_RE = /^[a-z][a-zA-Z0-9_]*$/;

const CANDIDATE_ATTR_NAMES = new Set([
  'placeholder', 'title', 'alt', 'aria-label', 'ariaLabel', 'label',
  'tooltip', 'description', 'subtitle', 'helperText', 'emptyMessage',
]);

function isTranslatable(text) {
  const s = (text || '').trim();
  if (!s || s.length < 2) return false;
  if (SKIP_RE.test(s)) return false;
  if (URL_RE.test(s)) return false;
  if (CODE_RE.test(s) && !TR_CHAR_RE.test(s)) return false;
  return TR_CHAR_RE.test(s) || TR_WORD_RE.test(s);
}

function slugify(text) {
  return text
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i').replace(/ş/g, 's').replace(/ğ/g, 'g')
    .replace(/ü/g, 'u').replace(/ö/g, 'o').replace(/ç/g, 'c')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40) || 'x';
}

function fileNamespace(relPath) {
  const bare = relPath
    .replace(/^src\//, '')
    .replace(/\.(jsx?|tsx?)$/, '')
    .replace(/[\/\\]/g, '_')
    .replace(/[^a-zA-Z0-9_]/g, '');
  return `cm.${bare}`;
}

function makeKey(ns, text, takenInFile) {
  const base = slugify(text);
  let key = `${ns}.${base}`;
  if (!takenInFile.has(key)) {
    takenInFile.add(key);
    return key;
  }
  const h = crypto.createHash('md5').update(text).digest('hex').slice(0, 5);
  key = `${ns}.${base}_${h}`;
  takenInFile.add(key);
  return key;
}

// Escape a string for use inside single-quoted JS string literal
function jsSingleQuote(s) {
  return "'" + s.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
}

// ── File discovery ───────────────────────────────────────────────────────────
function listCandidateFiles() {
  if (FILES_ARG) return FILES_ARG;
  const all = execSync(
    `find src/pages src/components -type f \\( -name '*.jsx' -o -name '*.tsx' \\) | sort`,
    { cwd: ROOT, encoding: 'utf8' }
  ).trim().split('\n').filter(Boolean);
  return all.filter(p => {
    const src = readFileSync(resolve(ROOT, p), 'utf8');
    if (/from ['"]react-i18next['"]/.test(src)) return false;
    return true;
  });
}

// ── Component body discovery ────────────────────────────────────────────────
/**
 * Returns array of { bodyStart, bodyEnd, insertOffset } where insertOffset is
 * the byte position immediately after the opening `{` of the BlockStatement
 * representing each component function's body.
 */
/**
 * Returns:
 *   { insertPoints: [{insertOffset}], anyComponentNeedsInjection: bool, hasComponent: bool }
 *
 * For each component-like function, we either:
 *  - Skip injection if `t` is already bound in scope (props destructure, param,
 *    local var, or existing useTranslation hook).
 *  - Otherwise emit an insertion point right after the body's opening `{`.
 */
function findComponentInsertPoints(ast) {
  const points = [];
  let hasComponent = false;

  // Helpers: is `t` bound by params/destructure/locals of this function?
  function paramsBindT(params) {
    for (const p of params) {
      if (t.isIdentifier(p) && p.name === 't') return true;
      if (t.isObjectPattern(p)) {
        for (const prop of p.properties) {
          if (t.isObjectProperty(prop) && t.isIdentifier(prop.key) && prop.key.name === 't') return true;
          if (t.isRestElement(prop)) continue;
        }
      }
      if (t.isAssignmentPattern(p) && t.isObjectPattern(p.left)) {
        for (const prop of p.left.properties) {
          if (t.isObjectProperty(prop) && t.isIdentifier(prop.key) && prop.key.name === 't') return true;
        }
      }
    }
    return false;
  }
  function bodyBindsT(body) {
    if (!t.isBlockStatement(body)) return false;
    for (const stmt of body.body) {
      if (!t.isVariableDeclaration(stmt)) continue;
      for (const d of stmt.declarations) {
        if (t.isIdentifier(d.id) && d.id.name === 't') return true;
        if (t.isObjectPattern(d.id)) {
          for (const prop of d.id.properties) {
            if (t.isObjectProperty(prop) && t.isIdentifier(prop.key) && prop.key.name === 't') return true;
          }
        }
      }
    }
    return false;
  }

  traverse(ast, {
    'FunctionDeclaration|FunctionExpression|ArrowFunctionExpression'(path) {
      const node = path.node;
      let name = null;
      if (t.isFunctionDeclaration(node) && node.id) name = node.id.name;
      else if (
        t.isVariableDeclarator(path.parent) && t.isIdentifier(path.parent.id)
      ) name = path.parent.id.name;
      if (!name || !/^[A-Z]/.test(name)) return;
      const body = node.body;
      if (!t.isBlockStatement(body)) return;
      let hasJsx = false;
      path.traverse({
        JSXElement() { hasJsx = true; path.stop(); },
        JSXFragment() { hasJsx = true; path.stop(); },
      });
      if (!hasJsx) return;
      hasComponent = true;
      // If `t` is already bound (via props, param, or local), skip injection
      if (paramsBindT(node.params) || bodyBindsT(body)) return;
      points.push({ insertOffset: body.start + 1 });
    },
  });
  return { insertPoints: points, hasComponent };
}

/**
 * Returns position info for adding/editing the react-i18next import:
 *   { mode: 'add', insertOffset, indent }       — no existing import; insert new
 *   { mode: 'extend', specEndOffset, indent }   — has import without useTranslation; add specifier
 *   { mode: 'noop' }                            — already imports useTranslation
 */
function findImportInsertPoint(ast, source) {
  let lastImport = null;
  let i18nImport = null;
  for (const node of ast.program.body) {
    if (!t.isImportDeclaration(node)) continue;
    lastImport = node;
    if (node.source.value === 'react-i18next') i18nImport = node;
  }
  if (i18nImport) {
    const has = i18nImport.specifiers.some(
      s => t.isImportSpecifier(s) && t.isIdentifier(s.imported)
        && s.imported.name === 'useTranslation'
    );
    if (has) return { mode: 'noop' };
    // Extend: append `, useTranslation` before closing `}` of specifier list
    const decl = source.slice(i18nImport.start, i18nImport.end);
    const closeBraceIdx = decl.lastIndexOf('}');
    if (closeBraceIdx === -1) return { mode: 'noop' };
    return {
      mode: 'extend',
      specInsertOffset: i18nImport.start + closeBraceIdx,
    };
  }
  if (!lastImport) {
    // No imports at all; insert at top of file
    return { mode: 'add', insertOffset: 0 };
  }
  // Add new import line right after the last import (after the trailing newline)
  let off = lastImport.end;
  if (source[off] === '\n') off += 1;
  return { mode: 'add', insertOffset: off };
}

// ── Per-file transform ───────────────────────────────────────────────────────
function transformFile(absPath, relPath) {
  const src = readFileSync(absPath, 'utf8');
  let ast;
  try {
    ast = parser.parse(src, {
      sourceType: 'module',
      plugins: ['jsx', 'classProperties', 'objectRestSpread', 'optionalChaining', 'nullishCoalescingOperator', 'topLevelAwait'],
      errorRecovery: false,
    });
  } catch (e) {
    return { ok: false, reason: 'parse_error', error: String(e.message || e).slice(0, 200) };
  }

  const ns = fileNamespace(relPath);
  const generatedKeys = new Set();
  const newKeyValues = {};

  // Pass 1: collect string-replacement edits with their byte ranges.
  // Each edit: { start, end, replacement }
  const edits = [];
  traverse(ast, {
    JSXText(p) {
      const node = p.node;
      const raw = node.value;
      const trimmed = raw.trim();
      if (!isTranslatable(trimmed)) return;
      const lead = raw.match(/^\s*/)[0];
      const trail = raw.match(/\s*$/)[0];
      const key = makeKey(ns, trimmed, generatedKeys);
      newKeyValues[key] = trimmed;
      // Replace ENTIRE JSXText node range with: lead + {t('key')} + trail
      const replacement = lead + `{t(${jsSingleQuote(key)})}` + trail;
      edits.push({ start: node.start, end: node.end, replacement });
    },
    JSXAttribute(p) {
      const node = p.node;
      const nameNode = node.name;
      const name = t.isJSXIdentifier(nameNode) ? nameNode.name
                : (t.isJSXNamespacedName(nameNode) ? `${nameNode.namespace.name}:${nameNode.name.name}` : null);
      if (!name || !CANDIDATE_ATTR_NAMES.has(name)) return;
      const v = node.value;
      if (!v || !t.isStringLiteral(v)) return;
      if (!isTranslatable(v.value)) return;
      const key = makeKey(ns, v.value, generatedKeys);
      newKeyValues[key] = v.value;
      // Replace just the StringLiteral value range with `{t('key')}`
      const replacement = `{t(${jsSingleQuote(key)})}`;
      edits.push({ start: v.start, end: v.end, replacement });
    },
  });

  if (edits.length === 0) {
    return { ok: false, reason: 'no_candidates' };
  }

  const { insertPoints: componentPoints, hasComponent } = findComponentInsertPoints(ast);
  if (!hasComponent) {
    return { ok: false, reason: 'no_component_function' };
  }

  // Build a master list of edits including import + hook injections.
  const HOOK_SNIPPET = `\n  const { t } = useTranslation();`;
  for (const cp of componentPoints) {
    edits.push({ start: cp.insertOffset, end: cp.insertOffset, replacement: HOOK_SNIPPET });
  }
  // Only add import if at least one component actually needs the hook
  if (componentPoints.length > 0) {
    const importPoint = findImportInsertPoint(ast, src);
    if (importPoint.mode === 'add') {
      edits.push({
        start: importPoint.insertOffset,
        end: importPoint.insertOffset,
        replacement: `import { useTranslation } from 'react-i18next';\n`,
      });
    } else if (importPoint.mode === 'extend') {
      edits.push({
        start: importPoint.specInsertOffset,
        end: importPoint.specInsertOffset,
        replacement: `, useTranslation `,
      });
    }
  }

  // Apply edits in DESCENDING order so byte offsets remain valid.
  edits.sort((a, b) => b.start - a.start);
  // Detect overlapping edits (parser bugs / nested matches) — defensive
  for (let i = 1; i < edits.length; i++) {
    const prev = edits[i - 1];
    const cur = edits[i];
    if (cur.end > prev.start && cur.start < prev.end) {
      return { ok: false, reason: 'overlapping_edits', error: `${cur.start}-${cur.end} vs ${prev.start}-${prev.end}` };
    }
  }
  let out = src;
  for (const e of edits) {
    out = out.slice(0, e.start) + e.replacement + out.slice(e.end);
  }

  // Sanity: re-parse output. If invalid, abort this file.
  try {
    parser.parse(out, {
      sourceType: 'module',
      plugins: ['jsx', 'classProperties', 'objectRestSpread', 'optionalChaining', 'nullishCoalescingOperator', 'topLevelAwait'],
    });
  } catch (e) {
    return { ok: false, reason: 'reparse_failed', error: String(e.message || e).slice(0, 200) };
  }

  return {
    ok: true,
    output: out,
    replacements: edits.filter(e => e.start !== e.end).length,
    newKeyValues,
    ns,
  };
}

// ── Locale JSON updates ──────────────────────────────────────────────────────
function setNested(obj, dottedKey, value) {
  const parts = dottedKey.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== 'object' || cur[parts[i]] === null) {
      cur[parts[i]] = {};
    }
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}
function getNested(obj, dottedKey) {
  const parts = dottedKey.split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur === null || typeof cur !== 'object' || !(p in cur)) return undefined;
    cur = cur[p];
  }
  return cur;
}

function updateLocales(allNewKeys) {
  const files = ['tr', 'en', 'de', 'fr', 'es', 'it', 'pt', 'ru', 'zh', 'ar'];
  const stats = {};
  for (const lng of files) {
    const path = resolve(LOCALES, `${lng}.json`);
    const data = JSON.parse(readFileSync(path, 'utf8'));
    let added = 0, kept = 0;
    for (const [key, trValue] of Object.entries(allNewKeys)) {
      const existing = getNested(data, key);
      if (existing !== undefined) { kept++; continue; }
      // tr → real value, others → TR placeholder (translator passes later)
      setNested(data, key, trValue);
      added++;
    }
    stats[lng] = { added, kept };
    if (APPLY) {
      writeFileSync(path, JSON.stringify(data, null, 2) + '\n', 'utf8');
    }
  }
  return stats;
}

// ── Main ─────────────────────────────────────────────────────────────────────
function main() {
  if (!existsSync(REPORT_DIR)) mkdirSync(REPORT_DIR, { recursive: true });
  const files = listCandidateFiles().slice(0, LIMIT);
  console.log(`Scanning ${files.length} candidate files…`);

  const report = {
    mode: APPLY ? 'apply' : 'dry',
    total: files.length,
    processed: [],
    skipped: [],
    failed: [],
  };
  const allNewKeys = {};

  for (const rel of files) {
    const abs = resolve(ROOT, rel);
    const result = transformFile(abs, rel);
    if (!result.ok) {
      if (result.reason === 'no_candidates' || result.reason === 'no_component_function') {
        report.skipped.push({ file: rel, reason: result.reason });
      } else {
        report.failed.push({ file: rel, reason: result.reason, error: result.error });
      }
      continue;
    }
    Object.assign(allNewKeys, result.newKeyValues);
    report.processed.push({ file: rel, replacements: result.replacements, ns: result.ns });
    if (PREVIEW && report.processed.length <= 1) {
      console.log(`\n===== PREVIEW: ${rel} =====\n${result.output}\n===== END PREVIEW =====\n`);
    }
    if (APPLY) writeFileSync(abs, result.output, 'utf8');
  }

  const localeStats = updateLocales(allNewKeys);

  report.localeStats = localeStats;
  report.totalNewKeys = Object.keys(allNewKeys).length;

  writeFileSync(resolve(REPORT_DIR, 'report.json'), JSON.stringify(report, null, 2));
  writeFileSync(resolve(REPORT_DIR, 'keys.json'), JSON.stringify(allNewKeys, null, 2));

  console.log('\n=== SUMMARY ===');
  console.log(`Mode:          ${report.mode}`);
  console.log(`Files scanned: ${report.total}`);
  console.log(`Processed:     ${report.processed.length}`);
  console.log(`Skipped:       ${report.skipped.length} (${
    report.skipped.filter(s => s.reason === 'no_candidates').length
  } no_candidates, ${
    report.skipped.filter(s => s.reason === 'no_component_function').length
  } no_component_function)`);
  console.log(`Failed:        ${report.failed.length}`);
  console.log(`New keys:      ${report.totalNewKeys}`);
  console.log(`Locale stats:  ${JSON.stringify(localeStats)}`);
  if (report.failed.length) {
    console.log('\nFailures:');
    report.failed.slice(0, 15).forEach(f => console.log(`  ${f.file}: ${f.reason} — ${f.error || ''}`));
  }
  console.log(`\nReport written to tools/codemod-i18n/{report,keys}.json`);
  if (!APPLY) console.log(`Run with --apply to write changes.`);
}

main();
