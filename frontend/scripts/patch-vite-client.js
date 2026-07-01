/**
 * Postinstall script: Patches Vite's HMR client to prevent automatic
 * page reloads when the WebSocket connection drops through a proxy.
 *
 * This script runs automatically after every `yarn install` and replaces
 * `location.reload()` calls in the Vite client with console logs.
 *
 * Why: Kubernetes/reverse-proxy environments drop idle WebSocket connections.
 * When the Vite HMR client detects a disconnect, it polls the server and then
 * calls location.reload(). In a proxied environment this creates a reload loop.
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

function patchViteClient() {
  if (!fs.existsSync(CLIENT_PATH)) {
    console.log('[patch-vite-client] Vite client not found, skipping patch.');
    return;
  }

  let content = fs.readFileSync(CLIENT_PATH, 'utf8');

  // Check if already patched
  if (content.includes('__SYROCE_HMR_PATCHED__')) {
    console.log('[patch-vite-client] Already patched, skipping.');
    return;
  }

  const originalCount = (content.match(/location\.reload\(\)/g) || []).length;

  // Replace all location.reload() calls with a console debug message
  content = content.replace(
    /location\.reload\(\)/g,
    'console.debug("[HMR] auto-reload suppressed by Syroce patch")'
  );

  // Add a marker so we can detect if it's already patched
  content = `// __SYROCE_HMR_PATCHED__\n${content}`;

  fs.writeFileSync(CLIENT_PATH, content, 'utf8');
  console.log(
    `[patch-vite-client] Patched ${originalCount} location.reload() calls in Vite client.`
  );
}

try {
  patchViteClient();
} catch (err) {
  // Non-fatal: the transformIndexHtml fallback in vite.config.js
  // will still protect against reloads at runtime.
  console.warn('[patch-vite-client] Patch failed (non-fatal):', err.message);
}
