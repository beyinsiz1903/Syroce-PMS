#!/usr/bin/env node
// Find JSX/TSX components that USE t(...) inside body but don't call useTranslation() — inject the hook.
import { readFileSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const files = process.argv.slice(2);
if (!files.length) { console.error('usage: node fix_missing_t_hook.mjs <files...>'); process.exit(1); }

let totalFixed = 0;
for (const file of files) {
  const orig = readFileSync(file, 'utf8');
  let src = orig;
  // Component start patterns:
  //  const Foo = (props) => {
  //  const Foo = ({...}) => {
  //  function Foo(props) {
  //  export default function Foo(props) {
  // PascalCase name
  const compRe = /(^|\n)\s*(?:export\s+(?:default\s+)?)?(?:const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*(?:React\.memo\(|memo\(|forwardRef\()?\s*\([^)]*?\)\s*=>\s*\{|function\s+([A-Z][A-Za-z0-9_]*)\s*\([^)]*?\)\s*\{)/gs;
  const fixes = [];
  let m;
  while ((m = compRe.exec(src)) !== null) {
    const name = m[2] || m[3];
    const openBraceIdx = m.index + m[0].length - 1; // position of opening {
    // Find matching close brace via brace counting (string/template aware roughly)
    let depth = 1, i = openBraceIdx + 1, inStr = null, inTpl = 0;
    while (i < src.length && depth > 0) {
      const c = src[i], p = src[i - 1];
      if (inStr) {
        if (c === inStr && p !== '\\') inStr = null;
      } else if (inTpl) {
        if (c === '`' && p !== '\\') inTpl--;
        else if (c === '$' && src[i + 1] === '{') { depth++; i += 2; continue; }
      } else {
        if (c === '"' || c === "'") inStr = c;
        else if (c === '`') inTpl++;
        else if (c === '/' && src[i + 1] === '/') { i = src.indexOf('\n', i); if (i < 0) break; }
        else if (c === '/' && src[i + 1] === '*') { i = src.indexOf('*/', i); if (i < 0) break; i += 2; continue; }
        else if (c === '{') depth++;
        else if (c === '}') depth--;
      }
      i++;
    }
    const bodyStart = openBraceIdx + 1, bodyEnd = i - 1;
    const body = src.slice(bodyStart, bodyEnd);
    // Strip nested function bodies for the "uses t" check? Hmm. Simpler: any "t(" outside of nested PascalCase decl.
    // We accept some over-matching: if body uses t( AND body does not have useTranslation(), inject.
    const usesT = /[^.\w]t\(/.test(body);
    const hasHook = /useTranslation\s*\(/.test(body);
    if (usesT && !hasHook) {
      fixes.push({ name, insertAt: bodyStart, openBraceIdx });
    }
  }
  if (!fixes.length) continue;
  // Apply from bottom to top
  fixes.sort((a, b) => b.insertAt - a.insertAt);
  for (const f of fixes) {
    const insert = `\n  const { t } = useTranslation();`;
    src = src.slice(0, f.insertAt) + insert + src.slice(f.insertAt);
  }
  // Ensure import exists
  if (!/from\s+['"]react-i18next['"]/.test(src)) {
    // add at top after first import
    src = `import { useTranslation } from 'react-i18next';\n` + src;
  } else if (!/useTranslation/.test(src.split('\n').filter(l => /from ['"]react-i18next['"]/.test(l)).join('\n'))) {
    src = src.replace(/import\s*\{([^}]*)\}\s*from\s*['"]react-i18next['"]/, (mm, inner) => {
      return `import { ${inner.trim()}, useTranslation } from 'react-i18next'`;
    });
  }
  writeFileSync(file, src);
  console.log(`FIXED ${file}: +${fixes.length} hook(s) → ${fixes.map(x => x.name).join(', ')}`);
  totalFixed += fixes.length;
}
console.log(`\nTotal: ${totalFixed} hook(s) inserted across ${files.length} file(s)`);
