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

function prefetchOne(name, importer) {
  if (prefetched.has(name)) return;
  prefetched.add(name);
  ric(() => {
    importer().catch(() => {
      prefetched.delete(name);
    });
  });
}

/**
 * Login sonrası çağrılır. Sık kullanılan ağır chunk'ları arka planda indirir.
 * Sıralama: en büyük + en sık kullanılan önce.
 */
export function prefetchHeavyModules() {
  prefetchOne('PMSModule', () => import('@/pages/PMSModule'));
  prefetchOne('ReservationCalendar', () => import('@/pages/ReservationCalendar'));
  // PMS tarihi geride kaldığında PMSDateBadge "Gün sonu işlemini yapın"
  // butonu çıkarıyor; kullanıcı bastığında chunk hazır olsun diye
  // login sonrası sessizce indirilir (734 satırlık ağır sayfa).
  prefetchOne('NightAuditDashboard', () => import('@/pages/NightAuditDashboard'));
}

// PMSDateBadge gibi az kullanılan ama tıklama anında ağır sayfaya
// yönlendiren UI elementleri için noktasal hover-prefetch helper'ı.
export function prefetchNightAudit() {
  prefetchOne('NightAuditDashboard', () => import('@/pages/NightAuditDashboard'));
}
