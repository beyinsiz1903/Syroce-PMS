/**
 * OfflineStatusBar — uygulama genelinde çevrimiçi/çevrimdışı durumunu ve
 * çevrimdışı check-in kuyruğunu (bekleyen / eşitlenen / çakışma) gösterir.
 *
 * - Çevrimiçi ve kuyruk boşsa hiçbir şey gösterilmez (sessiz).
 * - Çevrimdışıyken sabit bir uyarı şeridi gösterir.
 * - Eşitlenmeyi bekleyen / çakışan girişler için sayaç + işlem sunar.
 */
import React from 'react';
import { WifiOff, RefreshCw, AlertTriangle, Clock, CheckCircle2, X } from 'lucide-react';
import useOfflineCheckins from '@/hooks/useOfflineCheckins';

const OfflineStatusBar = () => {
  const {
    online,
    pendingCount,
    conflicts,
    conflictCount,
    stalePending,
    stalePendingCount,
    now,
    syncing,
    sync,
    retry,
    retryMany,
    cancel,
    cancelMany,
    dismiss,
  } = useOfflineCheckins();

  // Toplu eylem hedefleri: takılan bekleyen girişlerin tümü; çakışanlardan ise
  // yalnızca yeniden-denenebilir olanlar (gerçek iş çakışmaları tekrar denenmez).
  const stalePendingIds = stalePending.map((item) => item.id);
  const retryableConflictIds = conflicts.filter(isRetryableConflict).map((item) => item.id);
  const conflictIds = conflicts.map((item) => item.id);

  const hasQueue = pendingCount > 0 || conflictCount > 0;

  // Çevrimiçi ve kuyruk boş: gösterme.
  if (online && !hasQueue) {
    return null;
  }

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[60] flex flex-col"
      data-testid="offline-status-bar"
    >
      {!online && (
        <div
          className="flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-sm font-medium text-white"
          data-testid="offline-indicator"
          role="status"
        >
          <WifiOff className="h-4 w-4" aria-hidden="true" />
          <span>
            Cevrimdisi mod — internet baglantisi yok. Kayitli veriler okunabilir,
            yapilan check-in'ler baglanti gelince otomatik gonderilir.
          </span>
        </div>
      )}

      {online && pendingCount > 0 && (
        <div
          className="flex items-center justify-center gap-3 bg-slate-800 px-4 py-2 text-sm text-white"
          data-testid="offline-pending-bar"
          role="status"
        >
          <Clock className="h-4 w-4" aria-hidden="true" />
          <span>
            {pendingCount} check-in eşitlenmeyi bekliyor.
          </span>
          <button
            type="button"
            onClick={sync}
            disabled={syncing}
            className="inline-flex items-center gap-1 rounded-md border border-white/40 px-2 py-1 text-xs font-medium hover:bg-white/10 disabled:opacity-50"
            data-testid="offline-sync-now"
          >
            <RefreshCw className={`h-3 w-3 ${syncing ? 'animate-spin' : ''}`} aria-hidden="true" />
            {syncing ? 'Eşitleniyor...' : 'Şimdi eşitle'}
          </button>
        </div>
      )}

      {!online && pendingCount > 0 && (
        <div
          className="flex items-center justify-center gap-2 bg-slate-800 px-4 py-1.5 text-xs text-white"
          data-testid="offline-pending-count"
        >
          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{pendingCount} check-in kuyrukta, baglanti gelince gonderilecek.</span>
        </div>
      )}

      {stalePendingCount > 0 && (
        <div
          className="bg-amber-600 px-4 py-2 text-sm text-white"
          data-testid="offline-stale-bar"
          role="alert"
        >
          <div className="flex items-center justify-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            <span>
              {stalePendingCount} check-in uzun suredir eşitlenemedi — kontrol edin.
            </span>
          </div>
          {stalePendingCount > 1 && (
            <div
              className="mx-auto mt-1 flex max-w-3xl items-center justify-end gap-2"
              data-testid="offline-stale-bulk-actions"
            >
              <button
                type="button"
                onClick={() => retryMany(stalePendingIds)}
                className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                data-testid="offline-stale-retry-all"
              >
                <RefreshCw className="h-3 w-3" aria-hidden="true" />
                Tümünü yeniden dene
              </button>
              <button
                type="button"
                onClick={() => cancelMany(stalePendingIds)}
                className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                data-testid="offline-stale-cancel-all"
              >
                <X className="h-3 w-3" aria-hidden="true" />
                Tümünü iptal
              </button>
            </div>
          )}
          <ul className="mx-auto mt-1 max-w-3xl space-y-1">
            {stalePending.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-2 rounded bg-amber-700/60 px-2 py-1 text-xs"
                data-testid="offline-stale-item"
              >
                <span className="truncate">
                  Rezervasyon {item.bookingId}: {formatAge(item.createdAt, now)} bekliyor
                  {item.attempts ? `, ${item.attempts} deneme` : ''}.
                </span>
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => retry(item.id)}
                    className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                    data-testid="offline-stale-retry"
                  >
                    <RefreshCw className="h-3 w-3" aria-hidden="true" />
                    Yeniden dene
                  </button>
                  <button
                    type="button"
                    onClick={() => cancel(item.id)}
                    className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                    data-testid="offline-stale-cancel"
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                    Iptal
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {conflictCount > 0 && (
        <div
          className="bg-red-600 px-4 py-2 text-sm text-white"
          data-testid="offline-conflict-bar"
          role="alert"
        >
          <div className="flex items-center justify-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            <span>{conflictCount} check-in eşitlenemedi (cakisma) — operatör islemi gerekiyor.</span>
          </div>
          {conflictCount > 1 && (
            <div
              className="mx-auto mt-1 flex max-w-3xl items-center justify-end gap-2"
              data-testid="offline-conflict-bulk-actions"
            >
              {retryableConflictIds.length > 1 && (
                <button
                  type="button"
                  onClick={() => retryMany(retryableConflictIds)}
                  className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                  data-testid="offline-conflict-retry-all"
                >
                  <RefreshCw className="h-3 w-3" aria-hidden="true" />
                  Tümünü yeniden dene
                </button>
              )}
              <button
                type="button"
                onClick={() => cancelMany(conflictIds)}
                className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                data-testid="offline-conflict-dismiss-all"
              >
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                Tümünü temizle
              </button>
            </div>
          )}
          <ul className="mx-auto mt-1 max-w-3xl space-y-1">
            {conflicts.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-2 rounded bg-red-700/60 px-2 py-1 text-xs"
                data-testid="offline-conflict-item"
              >
                <span className="truncate">
                  Rezervasyon {item.bookingId}: {conflictMessage(item)}
                  {item.attempts ? ` (${item.attempts} deneme)` : ''}
                </span>
                <span className="flex items-center gap-1">
                  {isRetryableConflict(item) && (
                    <button
                      type="button"
                      onClick={() => retry(item.id)}
                      className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                      data-testid="offline-conflict-retry"
                    >
                      <RefreshCw className="h-3 w-3" aria-hidden="true" />
                      Yeniden dene
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => dismiss(item.id)}
                    className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                    data-testid="offline-conflict-dismiss"
                  >
                    <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                    Anladim
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

// Yapilandirilmis backend cakisma kodlarini Turkce operatör mesajina cevir.
function conflictMessage(item) {
  const detail = item.error;
  const code = (typeof detail === 'object' && detail?.code) || null;
  switch (code) {
    case 'ROOM_OCCUPIED':
      return 'Oda baskasi tarafindan dolduruldu.';
    case 'ROOM_NOT_READY':
      return 'Oda henuz hazir degil.';
    case 'INVALID_STATUS':
      return 'Rezervasyon durumu check-in icin uygun degil.';
    case 'NO_ROOM':
      return 'Rezervasyona oda atanmamis.';
    case 'MAX_RETRIES_EXCEEDED':
      return 'Tekrar tekrar denendi ama eşitlenemedi — yeniden deneyin veya iptal edin.';
    default:
      if (item.httpStatus === 404) return 'Rezervasyon bulunamadi (silinmis olabilir).';
      if (typeof detail === 'string') return detail;
      if (typeof detail === 'object' && detail?.message) return detail.message;
      return 'Bilinmeyen cakisma — manuel kontrol edin.';
  }
}

// Sadece geçici-tükenmiş (deneme tavanı) çakışmalar manuel yeniden denemeye
// uygundur; gerçek iş çakışmaları (404/409 vb.) tekrar denemekle düzelmez.
function isRetryableConflict(item) {
  const detail = item.error;
  const code = (typeof detail === 'object' && detail?.code) || null;
  return code === 'MAX_RETRIES_EXCEEDED';
}

// İlk kuyruğa alınma zamanından bu yana geçen süreyi insan-okunur Türkçe çevir.
function formatAge(createdAt, now) {
  if (!createdAt) return 'bir süredir';
  const ms = Math.max(0, (now || Date.now()) - createdAt);
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return `${minutes} dk`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} sa ${minutes % 60} dk`;
  const days = Math.floor(hours / 24);
  return `${days} gün ${hours % 24} sa`;
}

export default OfflineStatusBar;
