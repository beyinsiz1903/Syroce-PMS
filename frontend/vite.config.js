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
    // HMR through Replit's mTLS proxy:
    //   - host: must be the public REPLIT_DEV_DOMAIN, NOT localhost
    //     (otherwise the browser tries wss://localhost and gets ECONNREFUSED).
    //   - clientPort 443 because the browser hits the proxy on https/wss.
    //   - hmr is disabled when REPLIT_DEV_DOMAIN is missing (e.g. CI builds)
    //     so a missing env var never poisons the WS URL.
    hmr: process.env.REPLIT_DEV_DOMAIN
      ? {
          host: process.env.REPLIT_DEV_DOMAIN,
          clientPort: 443,
          protocol: 'wss',
          timeout: 15000,
        }
      : false,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Socket.IO mounts at /ws on the backend (see backend/server.py).
      // ws: true makes Vite tunnel the websocket upgrade through to the
      // backend so internal-chat real-time delivery works in dev too.
      '/ws': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  oxc: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
  build: {
    outDir: 'build',
    sourcemap: false,
    minify: true,
    target: 'es2020',
    cssMinify: true,
    chunkSizeWarningLimit: 500,
    // Modulepreload kontrolü: Vite varsayılan olarak entry'den ulaşılan tüm
    // vendor chunk'larını <link rel="modulepreload"> ile ilk paint'te indirir.
    // Bu, lazy route'larda kullanılan ağır vendor'ları gizlice startup
    // maliyetine ekler. Aşağıdaki filtre yalnızca gerçekten ilk render için
    // gerekli vendor'ları preload listesinde bırakır; diğerleri lazy chunk
    // dependency olarak kalır (sadece o page açılınca iner).
    modulepreload: {
      resolveDependencies(_filename, deps) {
        const skip = [
          'vendor-charts',  // recharts + d3 (~184 KB gzip), sadece dashboard'larda
          'vendor-pdf',     // jspdf + html2canvas, sadece export'larda
          'vendor-qr',      // html5-qrcode, sadece QR sayfalarında
          'vendor-motion',  // framer-motion, sadece animasyonlu yüzeylerde
          'vendor-socket',  // socket.io, login sonrası bağlanır
        ];
        return deps.filter((d) => !skip.some((s) => d.includes(s)));
      },
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/') || id.includes('node_modules/react-router') || id.includes('node_modules/scheduler')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/@tanstack')) {
            return 'vendor-query';
          }
          // recharts/d3/victory: manualChunks ile sabit "vendor-charts" yapmıyoruz.
          // Tüm kullanıcılar (31 sayfa/component) lazy route arkasında olduğu
          // için Rollup'ın doğal shared-chunk algoritması async chunk üretir
          // ve entry modulepreload listesine düşmez. Manuel chunk adlandırması
          // Vite'ın html transformation'ında bu chunk'ı "named static dep"
          // olarak ele alıp ilk paint'e enjekte ediyordu (~184 KB gzip).
          if (
            id.includes('node_modules/jspdf') ||
            id.includes('node_modules/html2canvas') ||
            id.includes('node_modules/canvg') ||
            id.includes('node_modules/dompurify')
          ) {
            return 'vendor-pdf';
          }
          if (id.includes('node_modules/@sentry')) {
            return 'vendor-sentry';
          }
          if (
            id.includes('node_modules/socket.io-client') ||
            id.includes('node_modules/engine.io-client') ||
            id.includes('node_modules/socket.io-parser') ||
            id.includes('node_modules/engine.io-parser')
          ) {
            return 'vendor-socket';
          }
          if (id.includes('node_modules/@radix-ui')) {
            return 'vendor-radix';
          }
          if (id.includes('node_modules/lucide-react')) {
            return 'vendor-icons';
          }
          if (
            id.includes('node_modules/react-hook-form') ||
            id.includes('node_modules/@hookform') ||
            id.includes('node_modules/zod') ||
            id.includes('node_modules/yup')
          ) {
            return 'vendor-forms';
          }
          if (
            id.includes('node_modules/i18next') ||
            id.includes('node_modules/react-i18next')
          ) {
            return 'vendor-i18n';
          }
          if (id.includes('node_modules/html5-qrcode') || id.includes('node_modules/qrcode')) {
            return 'vendor-qr';
          }
          if (id.includes('node_modules/framer-motion')) {
            return 'vendor-motion';
          }
          if (
            id.includes('node_modules/axios') ||
            id.includes('node_modules/date-fns') ||
            id.includes('node_modules/clsx') ||
            id.includes('node_modules/tailwind-merge') ||
            id.includes('node_modules/class-variance-authority') ||
            id.includes('node_modules/sonner')
          ) {
            return 'vendor-ui';
          }
          // Catch-all YOK: kalan node_modules paketleri için Rollup'ın
          // doğal split algoritması kullanılır. Tek "vendor-misc" kovası,
          // lazy route'a ait paketleri startup modulepreload'a sokarak
          // ilk yük maliyetini gizlice artırıyordu (T006 review bulgusu).
          return undefined;
        },
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'js/[name]-[hash].js',
        entryFileNames: 'js/[name]-[hash].js',
      },
    },
  },
});
