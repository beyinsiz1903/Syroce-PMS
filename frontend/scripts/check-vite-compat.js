#!/usr/bin/env node
/**
 * Upstream Vite Compatibility Check
 *
 * Verifies that the installed Vite version's client code still contains
 * the patterns we patch. If Vite changes its reload mechanism, this
 * script raises an alarm so the HMR guard can be updated.
 *
 * Run: node scripts/check-vite-compat.js
 * CI:  Add to pre-build or test stage
 */
const fs = require('fs');
const path = require('path');

const CLIENT_PATH = path.resolve(
  __dirname, '..', 'node_modules', 'vite', 'dist', 'client', 'client.mjs'
);

const EXPECTED_PATTERNS = [
  { name: 'location.reload() call', regex: /location\.reload\(\)/, required: false },
  { name: 'WebSocket reconnect logic', regex: /socket|WebSocket/i, required: true },
];

function check() {
  if (!fs.existsSync(CLIENT_PATH)) {
    console.warn('[vite-compat] Vite client not found at:', CLIENT_PATH);
    console.warn('[vite-compat] Skipping compatibility check (not installed yet).');
    process.exit(0);
  }

  const content = fs.readFileSync(CLIENT_PATH, 'utf8');
  const pkg = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, '..', 'node_modules', 'vite', 'package.json'), 'utf8')
  );
  const version = pkg.version;
  let warnings = 0;
  let errors = 0;

  console.log(`[vite-compat] Checking Vite v${version} client compatibility...\n`);

  for (const p of EXPECTED_PATTERNS) {
    const found = p.regex.test(content);
    if (found) {
      console.log(`  OK   ${p.name}`);
    } else if (p.required) {
      console.error(`  FAIL ${p.name} — pattern not found (breaking change?)`);
      errors++;
    } else {
      console.warn(`  WARN ${p.name} — pattern not found (may already be patched or changed upstream)`);
      warnings++;
    }
  }

  // Check if our patch was applied
  const patched = content.includes('reload suppressed');
  if (patched) {
    console.log(`  OK   postinstall patch is applied`);
  } else {
    console.warn(`  WARN postinstall patch not detected — run 'yarn install' or 'node scripts/patch-vite-client.js'`);
    warnings++;
  }

  console.log(`\n[vite-compat] Summary: ${errors} error(s), ${warnings} warning(s)`);

  if (errors > 0) {
    console.error('\n[vite-compat] BREAKING: Vite client structure has changed.');
    console.error('[vite-compat] The HMR reload guard may not work correctly.');
    console.error('[vite-compat] Review scripts/patch-vite-client.js and vite.config.js.');
    process.exit(1);
  }

  if (warnings > 0) {
    console.warn('\n[vite-compat] Non-critical changes detected. Monitor HMR behavior.');
  }

  process.exit(0);
}

check();
