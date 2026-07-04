/**
 * OfflineStatusBar — uygulama genelinde çevrimiçi/çevrimdışı durumunu ve ÜÇ
 * çevrimdışı kuyruğu (check-in, oda durumu, çıkış) bekleyen / eşitlenen /
 * çakışma olarak gösterir.
 *
 * - Çevrimiçi ve tüm kuyruklar boşsa hiçbir şey gösterilmez (sessiz).
 * - Çevrimdışıyken sabit bir uyarı şeridi gösterir.
 * - Her kuyruk türü için bekleyen / takılan / çakışan girişlerde sayaç + işlem.
 *
 * Check-in yolu DEĞİŞMEDİ: aynı kanca (useOfflinecheckins) + aynı test-id'ler
 * ('offline-pending-bar' vb.) generic bölüm bileşeniyle birebir korunur; oda
 * durumu ve çıkış paralel kancalarla ('offline-roomstatus-*', 'offline-checkout-*')
 * eklenir.
 */
import React from 'react';
import { WifiOff, RefreshCw, AlertTriangle, Clock, CheckCircle2, X } from 'lucide-react';
import useOfflineCheckins from '@/hooks/useOfflineCheckins';
import useOfflineRoomStatus from '@/hooks/useOfflineRoomStatus';
import useOfflineCheckouts from '@/hooks/useOfflineCheckouts';

const OfflineStatusBar = () => {
  const checkin = useOfflineCheckins();
  const roomStatus = useOfflineRoomStatus();
  const checkout = useOfflineCheckouts();

  // online tüm kancalarda aynı (navigator.onLine) — birini referans al.
  const online = checkin.online;

  const hasAnyQueue =
    checkin.pendingCount > 0 || checkin.conflictCount > 0 ||
    roomStatus.pendingCount > 0 || roomStatus.conflictCount > 0 ||
    checkout.pendingCount > 0 || checkout.conflictCount > 0;

  // Çevrimiçi ve tüm kuyruklar boş: gösterme.
  if (online && !hasAnyQueue) {
    return null;
  }

  return (
    <div
      className="relative z-[60] flex flex-col w-full"
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
            Çevrimdışı mod — internet bağlantısı yok. Kayıtlı veriler okunabilir;
            yapılan check-in, oda durumu ve çıkış işlemleri bağlantı gelince
            otomatik gönderilir.
          </span>
        </div>
      )}

      <OfflineQueueSection
        result={checkin}
        online={online}
        noun="check-in"
        itemLabel={(it) => `Rezervasyon ${it.bookingId}`}
        conflictMessage={checkinConflictMessage}
        testidPrefix="offline"
      />
      <OfflineQueueSection
        result={roomStatus}
        online={online}
        noun="oda durumu"
        itemLabel={(it) => `Oda ${it.roomId}`}
        conflictMessage={roomStatusConflictMessage}
        testidPrefix="offline-roomstatus"
      />
      <OfflineQueueSection
        result={checkout}
        online={online}
        noun="çıkış"
        itemLabel={(it) => `Rezervasyon ${it.bookingId}`}
        conflictMessage={checkoutConflictMessage}
        testidPrefix="offline-checkout"
      />
    </div>
  );
};

/**
 * Tek bir kuyruk türü için bekleyen/takılan/çakışan şeritleri ve işlemleri
 * render eder. check-in için testidPrefix="offline" ile mevcut test-id'ler
 * birebir korunur.
 */
function OfflineQueueSection({ result, online, noun, itemLabel, conflictMessage, testidPrefix }) {
  const {
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
  } = result;

  const stalePendingIds = stalePending.map((item) => item.id);
  const retryableConflictIds = conflicts.filter(isRetryableConflict).map((item) => item.id);
  const conflictIds = conflicts.map((item) => item.id);

  return (
    <>
      {online && pendingCount > 0 && (
        <div
          className="flex items-center justify-center gap-3 bg-slate-800 px-4 py-2 text-sm text-white"
          data-testid={`${testidPrefix}-pending-bar`}
          role="status"
        >
          <Clock className="h-4 w-4" aria-hidden="true" />
          <span>{pendingCount} {noun} eşitlenmeyi bekliyor.</span>
          <button
            type="button"
            onClick={sync}
            disabled={syncing}
            className="inline-flex items-center gap-1 rounded-md border border-white/40 px-2 py-1 text-xs font-medium hover:bg-white/10 disabled:opacity-50"
            data-testid={`${testidPrefix}-sync-now`}
          >
            <RefreshCw className={`h-3 w-3 ${syncing ? 'animate-spin' : ''}`} aria-hidden="true" />
            {syncing ? 'Eşitleniyor...' : 'Şimdi eşitle'}
          </button>
        </div>
      )}

      {!online && pendingCount > 0 && (
        <div
          className="flex items-center justify-center gap-2 bg-slate-800 px-4 py-1.5 text-xs text-white"
          data-testid={`${testidPrefix}-pending-count`}
        >
          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{pendingCount} {noun} kuyrukta, bağlantı gelince gönderilecek.</span>
        </div>
      )}

      {stalePendingCount > 0 && (
        <div
          className="bg-amber-600 px-4 py-2 text-sm text-white"
          data-testid={`${testidPrefix}-stale-bar`}
          role="alert"
        >
          <div className="flex items-center justify-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            <span>{stalePendingCount} {noun} uzun süredir eşitlenemedi — kontrol edin.</span>
          </div>
          {stalePendingCount > 1 && (
            <div
              className="mx-auto mt-1 flex max-w-3xl items-center justify-end gap-2"
              data-testid={`${testidPrefix}-stale-bulk-actions`}
            >
              <button
                type="button"
                onClick={() => retryMany(stalePendingIds)}
                className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                data-testid={`${testidPrefix}-stale-retry-all`}
              >
                <RefreshCw className="h-3 w-3" aria-hidden="true" />
                Tümünü yeniden dene
              </button>
              <button
                type="button"
                onClick={() => cancelMany(stalePendingIds)}
                className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                data-testid={`${testidPrefix}-stale-cancel-all`}
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
                data-testid={`${testidPrefix}-stale-item`}
              >
                <span className="truncate">
                  {itemLabel(item)}: {formatAge(item.createdAt, now)} bekliyor
                  {item.attempts ? `, ${item.attempts} deneme` : ''}.
                </span>
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => retry(item.id)}
                    className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                    data-testid={`${testidPrefix}-stale-retry`}
                  >
                    <RefreshCw className="h-3 w-3" aria-hidden="true" />
                    Yeniden dene
                  </button>
                  <button
                    type="button"
                    onClick={() => cancel(item.id)}
                    className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                    data-testid={`${testidPrefix}-stale-cancel`}
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
          data-testid={`${testidPrefix}-conflict-bar`}
          role="alert"
        >
          <div className="flex items-center justify-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            <span>{conflictCount} {noun} eşitlenemedi (çakışma) — operatör işlemi gerekiyor.</span>
          </div>
          {conflictCount > 1 && (
            <div
              className="mx-auto mt-1 flex max-w-3xl items-center justify-end gap-2"
              data-testid={`${testidPrefix}-conflict-bulk-actions`}
            >
              {retryableConflictIds.length > 1 && (
                <button
                  type="button"
                  onClick={() => retryMany(retryableConflictIds)}
                  className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                  data-testid={`${testidPrefix}-conflict-retry-all`}
                >
                  <RefreshCw className="h-3 w-3" aria-hidden="true" />
                  Tümünü yeniden dene
                </button>
              )}
              <button
                type="button"
                onClick={() => cancelMany(conflictIds)}
                className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 text-xs font-medium hover:bg-white/10"
                data-testid={`${testidPrefix}-conflict-dismiss-all`}
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
                data-testid={`${testidPrefix}-conflict-item`}
              >
                <span className="truncate">
                  {itemLabel(item)}: {conflictMessage(item)}
                  {item.attempts ? ` (${item.attempts} deneme)` : ''}
                </span>
                <span className="flex items-center gap-1">
                  {isRetryableConflict(item) && (
                    <button
                      type="button"
                      onClick={() => retry(item.id)}
                      className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                      data-testid={`${testidPrefix}-conflict-retry`}
                    >
                      <RefreshCw className="h-3 w-3" aria-hidden="true" />
                      Yeniden dene
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => dismiss(item.id)}
                    className="inline-flex items-center gap-1 rounded border border-white/40 px-2 py-0.5 font-medium hover:bg-white/10"
                    data-testid={`${testidPrefix}-conflict-dismiss`}
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
    </>
  );
}

// Check-in çakışma kodlarını Türkçe operatör mesajına çevir.
function checkinConflictMessage(item) {
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

// Oda-durumu çakışma kodlarını Türkçe operatör mesajına çevir.
function roomStatusConflictMessage(item) {
  const detail = item.error;
  const code = (typeof detail === 'object' && detail?.code) || null;
  if (code === 'MAX_RETRIES_EXCEEDED') {
    return 'Tekrar tekrar denendi ama eşitlenemedi — yeniden deneyin veya iptal edin.';
  }
  if (item.httpStatus === 404) return 'Oda bulunamadı (silinmiş olabilir).';
  if (item.httpStatus === 403) return 'Bu işlem için yetkiniz yok.';
  if (item.httpStatus === 422) return 'Geçersiz oda durumu.';
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail?.message) return detail.message;
  return 'Bilinmeyen çakışma — manuel kontrol edin.';
}

// Çıkış çakışma kodlarını Türkçe operatör mesajına çevir.
function checkoutConflictMessage(item) {
  const detail = item.error;
  const code = (typeof detail === 'object' && detail?.code) || null;
  if (code === 'OUTSTANDING_BALANCE' || item.httpStatus === 402) {
    return 'Açık bakiye oluştu — çevrimdışı kapatılamaz, lütfen ödeme alın.';
  }
  if (code === 'MAX_RETRIES_EXCEEDED') {
    return 'Tekrar tekrar denendi ama eşitlenemedi — yeniden deneyin veya iptal edin.';
  }
  if (item.httpStatus === 404) return 'Rezervasyon bulunamadı (silinmiş olabilir).';
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail?.message) return detail.message;
  return 'Bilinmeyen çakışma — manuel kontrol edin.';
}

// Sadece geçici-tükenmiş (deneme tavanı) çakışmalar manuel yeniden denemeye
// uygundur; gerçek iş çakışmaları (404/409/402 vb.) tekrar denemekle düzelmez.
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
