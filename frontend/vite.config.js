import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Permanent HMR reload suppression plugin for proxied environments.
 *
 * Problem: Kubernetes/reverse-proxy drops idle WebSocket connections after ~60s.
 *          When Vite's HMR client detects the disconnect, it calls location.reload()
 *          causing periodic full-page refreshes that destroy form state and UX.
 *
 * Solution (3 layers of defense):
 *   Layer 1 – postinstall script patches node_modules directly (see scripts/patch-vite-client.js)
 *   Layer 2 – transform hook catches any reload() calls that survive in bundled client code
 *   Layer 3 – transformIndexHtml injects a smart runtime guard that blocks reloads
 *             not triggered by user interaction (clicks, submits, keyboard)
 */
function hmrReloadGuard() {
  const enabled = process.env.VITE_HMR_GUARD_ENABLED !== 'false';
  return {
    name: 'hmr-reload-guard',
    enforce: 'pre',

    // Layer 2: Transform-time patch of Vite client code
    transform(code, id) {
      if (!enabled) return;
      if (id.includes('vite/dist/client') || id.includes('@vite/client')) {
        return code.replace(
          /location\.reload\(\)/g,
          'console.debug("[HMR] reload suppressed (transform)")'
        );
      }
    },

    // Layer 3: Runtime guard injected as the FIRST script in <head>
    transformIndexHtml(html) {
      if (!enabled) return html;
      const guardScript = `<script>
(function() {
  // Smart reload guard: allows user-initiated reloads, blocks HMR auto-reloads.
  // User interactions (click, submit, keydown) set a flag for 3 seconds.
  // location.reload() is only permitted while that flag is active.
  var _origReload = location.reload;
  var _userActive = false;
  var _activeTimer = null;

  function markActive() {
    _userActive = true;
    if (_activeTimer) clearTimeout(_activeTimer);
    _activeTimer = setTimeout(function() { _userActive = false; }, 3000);
  }

  document.addEventListener('click', markActive, true);
  document.addEventListener('submit', markActive, true);
  document.addEventListener('keydown', markActive, true);

  // Programmatic reload API: window.__syroceReload() always works
  window.__syroceReload = function() {
    _origReload.call(location);
  };

  try {
    Object.defineProperty(Location.prototype, 'reload', {
      configurable: true,
      enumerable: true,
      value: function() {
        if (_userActive) {
          _userActive = false;
          return _origReload.call(this);
        }
        console.debug('[Syroce] auto-reload blocked (no user interaction)');
      }
    });
  } catch(e) {
    // Fallback: simple override if defineProperty fails
    Location.prototype.reload = function() {
      if (_userActive) {
        _userActive = false;
        return _origReload.call(location);
      }
      console.debug('[Syroce] auto-reload blocked (fallback)');
    };
  }
})();
</script>`;

      return html.replace('<head>', '<head>' + guardScript);
    },
  };
}

export default defineConfig({
  plugins: [
    hmrReloadGuard(),
    react({
      include: /\.(jsx|tsx)$/,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5000,
    allowedHosts: true,
    hmr: {
      clientPort: 443,
      protocol: 'wss',
      // Shorter timeout = more frequent pings = WebSocket stays alive through proxy
      timeout: 15000,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: false,
    minify: true,
    target: 'es2020',
    cssMinify: true,
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/') || id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/@tanstack')) {
            return 'vendor-query';
          }
          if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-')) {
            return 'vendor-charts';
          }
          if (id.includes('node_modules/axios') || id.includes('node_modules/date-fns')) {
            return 'vendor-ui';
          }
        },
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'js/[name]-[hash].js',
        entryFileNames: 'js/[name]-[hash].js',
      },
    },
  },
});
