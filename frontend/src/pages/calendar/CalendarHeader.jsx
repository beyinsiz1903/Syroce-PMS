import React, { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Calendar as CalendarIcon, ChevronLeft, ChevronRight,
  Plus, RefreshCw, Loader2, AlertTriangle
} from "lucide-react";
import { getUnassignedUrgency } from "./calendarHelpers";
import { useTranslation } from 'react-i18next';

const CalendarHeader = ({
  dateRange,
  daysToShow,
  setDaysToShow,
  bookings,
  conflicts,
  syncing,
  onNavigatePrevious,
  onNavigateNext,
  onGoToDate,
  onSyncReservations,
  onShowFindRoomDialog,
  onShowNewBookingDialog,
  onShowUnassigned,
  onShowConflicts,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const unassignedList = bookings.filter(b => !b.room_id && b.status !== 'cancelled' && b.status !== 'checked_out' && b.status !== 'no_show');
  const unassignedCount = unassignedList.length;
  const overdueCount = unassignedList.filter(b => getUnassignedUrgency(b).level === 'overdue').length;
  const todayCount = unassignedList.filter(b => getUnassignedUrgency(b).level === 'today').length;
  const hasUrgent = overdueCount > 0 || todayCount > 0;
  // Native date picker — popover yok. "Tarihe Git" butonu hidden input'un
  // showPicker()'ını tetikler; tarayıcının kendi takvimi açılır, ←/→ ile
  // ay içinde gezilebilir, dış tıklama veya Esc ile kapanır (browser yönetir).
  const dateInputRef = useRef(null);
  const openNativePicker = () => {
    const el = dateInputRef.current;
    if (!el) return;
    if (typeof el.showPicker === 'function') {
      try { el.showPicker(); return; } catch (_) { /* fallback */ }
    }
    el.focus();
    el.click();
  };

  const dateRangeLabel = dateRange.length > 0
    ? `${dateRange[0].toLocaleDateString('tr-TR', { day: 'numeric', month: 'long' })} – ${dateRange[dateRange.length - 1].toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}`
    : '';

  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-2"
      data-testid="reservation-toolbar"
    >
      {/* ─── LEFT GROUP: title + date range + alert chips ─── */}
      <div className="flex items-center gap-3 min-w-0 mr-auto">
        <button
          type="button"
          onClick={() => navigate('/pms?tab=bookings')}
          className="flex items-center gap-2 group shrink-0"
          data-testid="reservations-tab-btn"
          title="Rezervasyon listesi"
        >
          <span className="flex items-center justify-center w-9 h-9 rounded-md bg-amber-50 text-amber-600 group-hover:bg-amber-100 transition-colors">
            <CalendarIcon className="w-5 h-5" />
          </span>
          <span className="flex flex-col leading-tight text-left min-w-0">
            <span className="text-base font-bold text-gray-900 group-hover:text-amber-600 transition-colors">
              Rezervasyonlar
            </span>
            {dateRangeLabel && (
              <span className="text-xs text-gray-500 font-medium truncate" data-testid="toolbar-date-range">
                {dateRangeLabel}
              </span>
            )}
          </span>
        </button>

        {unassignedCount > 0 && (
          <button
            type="button"
            className={`font-medium text-xs px-2.5 h-8 rounded-md border cursor-pointer flex items-center whitespace-nowrap ${
              overdueCount > 0
                ? 'border-red-400 text-red-700 bg-red-50 hover:bg-red-100 animate-pulse'
                : 'border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100'
            }`}
            data-testid="unassigned-count-btn"
            onClick={() => onShowUnassigned?.()}
          >
            {hasUrgent && <AlertTriangle className="w-3.5 h-3.5 mr-1" />}
            {unassignedCount} {t('cm.pages_calendar_CalendarHeader.atanmamis')}
            {overdueCount > 0 && <span className="ml-1 text-red-600 font-bold">({overdueCount} {t('cm.pages_calendar_CalendarHeader.gecikmis')}</span>}
            {overdueCount === 0 && todayCount > 0 && <span className="ml-1 text-amber-600 font-bold">({todayCount} {t('cm.pages_calendar_CalendarHeader.bugun')}</span>}
          </button>
        )}

        {conflicts.length > 0 && (
          <button
            type="button"
            className="h-8 px-2.5 rounded-md bg-red-500 hover:bg-red-600 animate-pulse text-white text-xs gap-1 flex items-center whitespace-nowrap"
            onClick={() => onShowConflicts?.()}
            data-testid="conflicts-btn"
            title={t('cm.pages_calendar_CalendarHeader.cakisan_rezervasyonlari_goruntule')}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            {conflicts.length} {t('cm.pages_calendar_CalendarHeader.cakisma')}
          </button>
        )}
      </div>

      {/* ─── MIDDLE GROUP: date navigation ─── */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Button
          variant="outline"
          size="sm"
          onClick={onNavigatePrevious}
          className="h-8 w-8 p-0"
          data-testid="calendar-nav-prev"
          title="Önceki"
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onGoToDate(new Date())}
          className="h-8 px-3 text-xs font-medium"
          data-testid="calendar-nav-today"
        >
          {t('cm.pages_calendar_CalendarHeader.bugun_01475')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onNavigateNext}
          className="h-8 w-8 p-0"
          data-testid="calendar-nav-next"
          title="Sonraki"
        >
          <ChevronRight className="w-4 h-4" />
        </Button>
        <div className="relative inline-flex items-center">
          <Button
            variant="outline"
            size="sm"
            onClick={openNativePicker}
            className="h-8 px-3 text-xs font-medium"
            data-testid="calendar-date-jump"
          >
            <CalendarIcon className="w-3.5 h-3.5 mr-1.5" />
            Tarihe Git
          </Button>
          <input
            ref={dateInputRef}
            type="date"
            data-testid="go-to-date-input"
            className="sr-only absolute inset-0 opacity-0 pointer-events-none"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(e) => {
              if (e.target.value) onGoToDate(new Date(e.target.value + 'T00:00:00'));
            }}
          />
        </div>
      </div>

      {/* ─── RIGHT GROUP: sync / view / overview / status / primary CTA ─── */}
      <div className="flex flex-wrap items-center gap-2 ml-auto">
        <Button
          variant="outline"
          size="sm"
          onClick={onSyncReservations}
          disabled={syncing}
          data-testid="ota-sync-button"
          className="text-xs h-8"
        >
          {syncing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1" />}
          {syncing ? 'Senkronize...' : 'OTA Sync'}
        </Button>

        <select
          className="border border-gray-300 rounded-md px-2 text-xs h-8 bg-white"
          value={daysToShow}
          onChange={(e) => setDaysToShow(Number(e.target.value))}
          data-testid="reservation-view-range-select"
        >
          <option value={7}>7 Gun</option>
          <option value={14}>14 Gun</option>
          <option value={30}>30 Gun</option>
        </select>

        <Button
          variant="outline"
          size="sm"
          onClick={onShowFindRoomDialog}
          className="text-xs h-8"
          data-testid="find-room-btn"
        >
          {t('cm.pages_calendar_CalendarHeader.genel_bakis')}
        </Button>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-600 whitespace-nowrap">{t('cm.pages_calendar_CalendarHeader.rezervasyon_durumu')}</span>
          <select
            className="border border-gray-300 rounded-md px-2 text-xs h-8 bg-white"
            data-testid="reservation-status-filter"
          >
            <option>Hepsi</option>
          </select>
        </div>

        <Button
          onClick={onShowNewBookingDialog}
          className="bg-amber-500 hover:bg-amber-600 text-white text-xs h-8 px-3.5 font-semibold shadow-sm"
          data-testid="add-reservation-button"
        >
          <Plus className="w-3.5 h-3.5 mr-1" />
          {t('cm.pages_calendar_CalendarHeader.rezervasyon_ekle')}
        </Button>
      </div>
    </div>
  );
};

export default CalendarHeader;
