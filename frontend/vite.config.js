import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Plugin to patch the Vite HMR client to prevent full-page reloads
// when the WebSocket connection drops through Kubernetes proxy
function patchHmrClient() {
  return {
    name: 'patch-hmr-client',
    enforce: 'pre',
    transform(code, id) {
      // Patch the @vite/client module to replace location.reload() with no-op
      if (id.includes('vite/dist/client') || id.includes('@vite/client')) {
        return code.replace(/location\.reload\(\)/g, 'console.debug("[HMR] reload suppressed")');
      }
    },
    transformIndexHtml(html) {
      // Inject a script to intercept Vite client reload behavior
      const patchScript = `<script>
(function(){
  var _orig = HTMLElement.prototype.remove;
  // Monkey-patch Location.prototype.reload to suppress Vite HMR reloads
  try {
    var origReload = Location.prototype.reload;
    Location.prototype.reload = function() {
      console.debug('[HMR] page reload suppressed');
    };
    window.__emergentForceReload = function() { origReload.call(location); };
  } catch(e) {}
})();
</script>`;
      return html.replace('<head>', '<head>' + patchScript);
    },
  };
}

export default defineConfig({
  plugins: [
    patchHmrClient(),
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
    port: 3000,
    allowedHosts: true,
    hmr: {
      clientPort: 443,
      protocol: 'wss',
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
  },
});
