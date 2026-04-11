/**
 * Utility to remove the Syroce HMR patch from Vite's client.
 * Run: node scripts/unpatch-vite-client.js
 *
 * After running this, do `yarn install` to restore the original +
 * re-apply the patch, or just leave it unpatched if no longer needed.
 */

const fs = require('fs');
const path = require('path');

const CLIENT_PATH = path.join(
  __dirname,
  '..',
  'node_modules',
  'vite',
  'dist',
  'client',
  'client.mjs'
);

if (!fs.existsSync(CLIENT_PATH)) {
  console.log('[unpatch] Vite client not found.');
  process.exit(0);
}

let content = fs.readFileSync(CLIENT_PATH, 'utf8');

if (!content.includes('__SYROCE_HMR_PATCHED__')) {
  console.log('[unpatch] Not patched, nothing to do.');
  process.exit(0);
}

// Remove the marker line
content = content.replace('// __SYROCE_HMR_PATCHED__\n', '');

// Restore location.reload() calls
content = content.replace(
  /console\.debug\("\[HMR\] auto-reload suppressed by Syroce patch"\)/g,
  'location.reload()'
);

fs.writeFileSync(CLIENT_PATH, content, 'utf8');
console.log('[unpatch] Vite client restored to original.');
