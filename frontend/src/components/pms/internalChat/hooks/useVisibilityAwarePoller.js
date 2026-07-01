import { useEffect, useRef } from 'react';

/**
 * Sekme görünürken `tick`'i `intervalMs`'de bir çağırır; sekme arka plana
 * geçince timer'ı durdurur, geri gelince hem hemen bir tetikleme yapar hem
 * timer'ı yeniden başlatır.
 *
 * `enabled=false` iken hiç başlamaz (örn. seçili thread yokken thread polling
 * koşturmasın diye). `tick` referansı her render değişebilir; ref tutarak
 * effect'in deps'inden çıkarıyoruz — aksi halde her render timer reset olurdu.
 */
export function useVisibilityAwarePoller(tick, { enabled = true, intervalMs = 60000 } = {}) {
  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  }, [tick]);

  useEffect(() => {
    if (!enabled) return undefined;
    let timer = null;
    const start = () => {
      if (timer !== null || document.hidden) return;
      timer = setInterval(() => {
        try { tickRef.current?.(); } catch { /* noop */ }
      }, intervalMs);
    };
    const stop = () => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };
    const onVis = () => {
      if (document.hidden) {
        stop();
      } else {
        try { tickRef.current?.(); } catch { /* noop */ }
        start();
      }
    };
    start();
    document.addEventListener('visibilitychange', onVis);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [enabled, intervalMs]);
}
