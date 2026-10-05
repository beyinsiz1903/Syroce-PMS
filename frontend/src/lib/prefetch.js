/**
 * Idle prefetch — kullanıcı oturum açtıktan sonra büyük lazy chunk'ları
 * arka planda sessizce indirir. Tıklandığında anında açılır (network-bound
 * gecikme ortadan kalkar).
 *
 * - requestIdleCallback varsa onu kullanır (tarayıcı boş olduğunda).
 * - Yoksa 1.5sn sonra setTimeout fallback (initial render bitsin diye).
 * - Hata yutulur (network sorunu kullanıcıyı engellemez).
 * - Aynı chunk iki kez prefetch edilmez (dynamic import zaten cache'ler).
 */

// timeout=2500ms: main thread çok meşgul kalsa bile prefetch en geç ~2.5sn
// içinde tetiklenir (yoksa idle hiç gelmeyebilir → starvation).
const ric =
  typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function'
    ? (cb) => window.requestIdleCallback(cb, { timeout: 2500 })
    : (cb) => setTimeout(() => cb({ didTimeout: true, timeRemaining: () => 0 }), 1500);

const prefetched = new Set();
let scheduledHeavyPrefetch = null;

export function canPrefetchHeavyModules(connection = typeof navigator !== 'undefined' ? navigator.connection : null) {
  // Background chunks must never compete with the page the operator is trying
  // to open. Hover/focus preloading in the navigation remains available on
  // every connection; this only governs the automatic post-login batch.
  if (!connection) return true;
  if (connection.saveData) return false;
  return !['slow-2g', '2g', '3g'].includes(connection.effectiveType);
}

function prefetchOne(name, importer) {
  if (prefetched.has(name)) return Promise.resolve();
  prefetched.add(name);
  return new Promise((resolve) => {
    ric(() => {
      importer().catch(() => {
        prefetched.delete(name);
      }).finally(resolve);
    });
  });
}

/**
 * Login sonrası çağrılır. Sık kullanılan ağır chunk'ları arka planda indirir.
 * Sıralama: en büyük + en sık kullanılan önce.
 */
export async function prefetchHeavyModules() {
  if (!canPrefetchHeavyModules()) return;
  // Run one chunk at a time. The previous parallel imports saturated slower
  // connections immediately after login, delaying the dashboard and the
  // first navigation even though the chunks were only speculative.
  await prefetchOne('PMSModule', () => import('@/pages/PMSModule'));
  await prefetchOne('ReservationCalendar', () => import('@/pages/ReservationCalendar'));
  // PMS tarihi geride kaldığında PMSDateBadge "Gün sonu işlemini yapın"
  // butonu çıkarıyor; kullanıcı bastığında chunk hazır olsun diye
  // login sonrası sessizce indirilir (734 satırlık ağır sayfa).
  await prefetchOne('NightAuditDashboard', () => import('@/pages/NightAuditDashboard'));
}

// Dashboard ve doğrulama istekleri ilk birkaç saniyede kritik yoldadır.
// Otomatik chunk indirme ancak ilk ekranın ağ ve render işi sakinleştikten
// sonra başlar. Kullanıcı menüye hover/focus yaptığında `preloadRoute` yine
// anında ön yükleme yaptığı için doğrudan navigasyon gecikmez.
export function scheduleHeavyModulePrefetch({ delay = 6000 } = {}) {
  if (scheduledHeavyPrefetch) return scheduledHeavyPrefetch.cancel;
  if (!canPrefetchHeavyModules()) return () => {};

  const timer = setTimeout(() => {
    scheduledHeavyPrefetch = null;
    void prefetchHeavyModules();
  }, delay);
  const cancel = () => {
    clearTimeout(timer);
    if (scheduledHeavyPrefetch?.cancel === cancel) scheduledHeavyPrefetch = null;
  };
  scheduledHeavyPrefetch = { cancel };
  return cancel;
}

// PMSDateBadge gibi az kullanılan ama tıklama anında ağır sayfaya
// yönlendiren UI elementleri için noktasal hover-prefetch helper'ı.
export function prefetchNightAudit() {
  prefetchOne('NightAuditDashboard', () => import('@/pages/NightAuditDashboard'));
}
