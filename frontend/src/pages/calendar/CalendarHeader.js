import React from "react";
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
  onGoToToday,
  onSyncReservations,
  onToggleEnterprise,
  onToggleAI,
  onShowFindRoomDialog,
  onShowNewBookingDialog,
}) => {
  const unassignedCount = bookings.filter(b => !b.room_id && b.status !== 'cancelled').length;

  return (
    <>
      {/* Header - PMS Style */}
      <div className="flex items-center justify-between" data-testid="calendar-header">
        <div className="flex items-center gap-2">
          <Button
            className="bg-orange-500 hover:bg-orange-600 text-white font-semibold px-4 py-2 rounded-md text-sm"
            data-testid="reservations-tab-btn"
          >
            <CalendarIcon className="w-4 h-4 mr-1.5" />
            Rezervasyonlar
          </Button>
          {unassignedCount > 0 && (
            <Button
              variant="outline"
              className="border-orange-300 text-orange-700 bg-orange-50 hover:bg-orange-100 font-medium text-sm px-3 py-2 rounded-md"
              data-testid="unassigned-count-btn"
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
          <Button variant="outline" size="sm" onClick={onGoToToday} className="h-8 px-3 text-xs font-medium" data-testid="go-today-btn">
            Tarihe git
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
