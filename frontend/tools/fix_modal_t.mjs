#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';
const files = process.argv.slice(2);
for (const f of files) {
  let src = readFileSync(f, 'utf8');
  const orig = src;
  // 1. Add import if missing
  if (!/from\s+['"]react-i18next['"]/.test(src)) {
    src = src.replace(/(import [^\n]+\n)/, `$1import { useTranslation } from 'react-i18next';\n`);
  } else if (!/useTranslation/.test(src)) {
    src = src.replace(/import\s*\{([^}]*)\}\s*from\s*['"]react-i18next['"]/, (m, inner) => `import { ${inner.trim()}, useTranslation } from 'react-i18next'`);
  }
  // 2. Remove `, t` or `t, ` or `, t }` from props destructure
  src = src.replace(/(\{\s*[^}]*?),\s*t\s*(\}\s*=\s*props)/g, '$1$2');
  src = src.replace(/(\{\s*)t\s*,\s*/g, '$1');  // t at start
  // 3. Add `const { t } = useTranslation();` after `} = props;` or `function X(props) {`
  // Match: `const { ... } = props;` and add hook after it.
  if (!/const\s*\{\s*t\s*\}\s*=\s*useTranslation\(\)/.test(src)) {
    src = src.replace(/(\}\s*=\s*props;\s*\n)/, `$1  const { t } = useTranslation();\n`);
  }
  if (src !== orig) {
    writeFileSync(f, src);
    console.log(`FIXED ${f}`);
  } else {
    console.log(`UNCHANGED ${f}`);
  }
}
