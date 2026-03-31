import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Calendar as CalendarIcon, ChevronLeft, ChevronRight,
  Plus, RefreshCw, Loader2
} from "lucide-react";

const CalendarHeader = ({
  dateRange,
  daysToShow,
  setDaysToShow,
  bookings,
  conflicts,
  syncing,
  showEnterprisePanel,
  showAIPanel,
  onNavigatePrevious,
  onNavigateNext,
  onGoToDate,
  onSyncReservations,
  onToggleEnterprise,
  onToggleAI,
  onShowFindRoomDialog,
  onShowNewBookingDialog,
  onShowUnassigned,
}) => {
  const navigate = useNavigate();
  const unassignedCount = bookings.filter(b => !b.room_id && b.status !== 'cancelled' && b.status !== 'checked_out').length;
  const [showDatePicker, setShowDatePicker] = useState(false);
  const datePickerRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (datePickerRef.current && !datePickerRef.current.contains(e.target)) setShowDatePicker(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <>
      {/* Header - PMS Style */}
      <div className="flex items-center justify-between" data-testid="calendar-header">
        <div className="flex items-center gap-2">
          <Button
            className="bg-orange-500 hover:bg-orange-600 text-white font-semibold px-4 py-2 rounded-md text-sm"
            data-testid="reservations-tab-btn"
            onClick={() => navigate('/pms?tab=bookings')}
          >
            <CalendarIcon className="w-4 h-4 mr-1.5" />
            Rezervasyonlar
          </Button>
          {unassignedCount > 0 && (
            <Button
              variant="outline"
              className="border-orange-300 text-orange-700 bg-orange-50 hover:bg-orange-100 font-medium text-sm px-3 py-2 rounded-md cursor-pointer"
              data-testid="unassigned-count-btn"
              onClick={() => onShowUnassigned?.()}
            >
              {unassignedCount} atanmamis oda
            </Button>
          )}
          {conflicts.length > 0 && (
            <Badge className="bg-red-500 animate-pulse text-white text-xs px-2 py-1">
              {conflicts.length} Cakisma
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onNavigatePrevious} className="h-8 w-8 p-0" data-testid="nav-prev-btn">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <div className="relative" ref={datePickerRef}>
            <Button variant="outline" size="sm" onClick={() => setShowDatePicker(!showDatePicker)} className="h-8 px-3 text-xs font-medium" data-testid="go-today-btn">
              Tarihe Git
            </Button>
            {showDatePicker && (
              <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 z-50 bg-white border rounded-lg shadow-lg p-3" data-testid="date-picker-popup">
                <input
                  type="date"
                  className="border rounded-md px-3 py-2 text-sm w-44"
                  data-testid="go-to-date-input"
                  autoFocus
                  onChange={(e) => {
                    if (e.target.value) {
                      onGoToDate(new Date(e.target.value + 'T00:00:00'));
                      setShowDatePicker(false);
                    }
                  }}
                />
                <div className="mt-2 flex gap-1">
                  <Button size="sm" variant="outline" className="h-7 text-xs flex-1" onClick={() => { onGoToDate(new Date()); setShowDatePicker(false); }}>Bugun</Button>
                </div>
              </div>
            )}
          </div>
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
            Genel Bakis
          </Button>
          <Button
            onClick={onShowNewBookingDialog}
            className="bg-orange-500 hover:bg-orange-600 text-white text-xs h-8 px-3 font-semibold"
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
              {dateRange[0].toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })} – {dateRange[dateRange.length - 1].toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' })}
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
              variant={showEnterprisePanel ? "default" : "outline"}
              onClick={onToggleEnterprise}
              className="h-7 text-xs px-2"
              data-testid="enterprise-toggle"
            >
              Ayarlar
            </Button>
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
