import React, { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Calendar as CalendarIcon, ChevronLeft, ChevronRight,
  Plus, RefreshCw, Loader2, AlertTriangle
} from "lucide-react";
import { getUnassignedUrgency } from "./calendarHelpers";

const CalendarHeader = ({
  dateRange,
  daysToShow,
  setDaysToShow,
  bookings,
  conflicts,
  syncing,
  showAIPanel,
  onNavigatePrevious,
  onNavigateNext,
  onGoToDate,
  onSyncReservations,
  onToggleAI,
  onShowFindRoomDialog,
  onShowNewBookingDialog,
  onShowUnassigned,
  onShowConflicts,
}) => {
  const navigate = useNavigate();
  const unassignedList = bookings.filter(b => !b.room_id && b.status !== 'cancelled' && b.status !== 'checked_out' && b.status !== 'no_show');
  const unassignedCount = unassignedList.length;
  const overdueCount = unassignedList.filter(b => getUnassignedUrgency(b).level === 'overdue').length;
  const todayCount = unassignedList.filter(b => getUnassignedUrgency(b).level === 'today').length;
  const hasUrgent = overdueCount > 0 || todayCount > 0;
  // Native date picker — popover yok. Tarihe Git butonu hidden input'un
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

  return (
    <>
      {/* Header - PMS Style */}
      <div className="flex items-center justify-between" data-testid="calendar-header">
        <div className="flex items-center gap-2">
          <Button
            className="bg-amber-500 hover:bg-amber-600 text-white font-semibold px-4 py-2 rounded-md text-sm"
            data-testid="reservations-tab-btn"
            onClick={() => navigate('/pms?tab=bookings')}
          >
            <CalendarIcon className="w-4 h-4 mr-1.5" />
            Rezervasyonlar
          </Button>
          {unassignedCount > 0 && (
            <Button
              variant="outline"
              className={`font-medium text-sm px-3 py-2 rounded-md cursor-pointer ${
                overdueCount > 0
                  ? 'border-red-400 text-red-700 bg-red-50 hover:bg-red-100 animate-pulse'
                  : todayCount > 0
                    ? 'border-amber-400 text-amber-700 bg-amber-50 hover:bg-amber-100'
                    : 'border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100'
              }`}
              data-testid="unassigned-count-btn"
              onClick={() => onShowUnassigned?.()}
            >
              {hasUrgent && <AlertTriangle className="w-3.5 h-3.5 mr-1" />}
              {unassignedCount} atanmamış
              {overdueCount > 0 && <span className="ml-1 text-red-600 font-bold">({overdueCount} gecikmiş!)</span>}
              {overdueCount === 0 && todayCount > 0 && <span className="ml-1 text-amber-600 font-bold">({todayCount} bugün)</span>}
            </Button>
          )}
          {conflicts.length > 0 && (
            <Button
              size="sm"
              className="h-7 px-2 py-1 bg-red-500 hover:bg-red-600 animate-pulse text-white text-xs gap-1"
              onClick={() => onShowConflicts?.()}
              data-testid="conflicts-btn"
              title="Çakışan rezervasyonları görüntüle"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              {conflicts.length} Çakışma
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onNavigatePrevious} className="h-8 w-8 p-0" data-testid="nav-prev-btn">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <div className="relative inline-flex items-center">
            <Button variant="outline" size="sm" onClick={openNativePicker} className="h-8 px-3 text-xs font-medium" data-testid="go-today-btn">
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
          <Button variant="outline" size="sm" onClick={() => onGoToDate(new Date())} className="h-8 px-3 text-xs font-medium" data-testid="go-today-shortcut-btn">
            Bugün
          </Button>
          <Button variant="outline" size="sm" onClick={onNavigateNext} className="h-8 w-8 p-0" data-testid="nav-next-btn">
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onSyncReservations}
            disabled={syncing}
            data-testid="sync-reservations-btn"
            className="text-xs h-8"
          >
            {syncing ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1" />}
            {syncing ? 'Senkronize...' : 'OTA Sync'}
          </Button>
          <select
            className="border rounded-md px-2 py-1 text-xs h-8"
            value={daysToShow}
            onChange={(e) => setDaysToShow(Number(e.target.value))}
            data-testid="days-selector"
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
            Genel Bakış
          </Button>
          <Button
            onClick={onShowNewBookingDialog}
            className="bg-amber-500 hover:bg-amber-600 text-white text-xs h-8 px-3 font-semibold"
            data-testid="add-reservation-btn"
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            Rezervasyon ekle
          </Button>
        </div>
      </div>

      {/* Date Range & Filters Row */}
      <div className="flex items-center justify-between bg-white border rounded-lg px-4 py-2" data-testid="date-range-bar">
        <div className="text-sm font-semibold text-gray-800">
          {dateRange.length > 0 && (
            <>
              {dateRange[0].toLocaleDateString('tr-TR', { day: 'numeric', month: 'long' })} – {dateRange[dateRange.length - 1].toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-gray-600">
            <span>Rezervasyon durumu</span>
            <select className="border rounded px-2 py-1 text-xs" data-testid="status-filter">
              <option>Hepsi</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={showAIPanel ? "default" : "outline"}
              onClick={onToggleAI}
              className="h-7 text-xs px-2"
              data-testid="ai-toggle"
            >
              Renklendirme
            </Button>
          </div>
        </div>
      </div>
    </>
  );
};

export default CalendarHeader;
