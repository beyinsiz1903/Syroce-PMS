import React, { useState, useMemo } from "react";
import { Calendar as CalendarIcon, Plus, ChevronDown, ChevronRight } from "lucide-react";
import {
  toDateStringUTC, isBookingOnDate, isBookingStart, isWeekend, isToday, isPastDate,
  formatDateWithDay, getBookingForRoomOnDate, getRoomBlockForDate,
  isBlockStart, calculateBlockSpan, calculateBookingSpan,
  getBookingStatusColor, getBookingStatus, getSourceColor,
  getUnassignedBookingsForType, computeUnassignedLanes,
  getUnassignedUrgency,
  isBlockedRoomStatus, cellOccupancyStatus, getCellOccupancyTint,
} from "./calendarHelpers";
import { useTranslation } from 'react-i18next';
import OccupancyBand from "./OccupancyBand";
import { compactGuestName, formatGuestName } from './roomTypeMatching';

// Readable grid constants. The old 72×38 cells made names and channel data
// difficult to scan on a reception desk display.
const CELL_W = 84;
const CELL_CLS = 'w-[84px]';
const LABEL_CLS = 'w-36';
const CELL_H = 48;
const BOOKING_H = 40;
const LANE_H = 40;
const LANE_BAR_H = 44;

export const clearCalendarTextSelection = () => {
  window.getSelection?.()?.removeAllRanges();
};

const CalendarGrid = ({
  rooms,
  bookings,
  roomBlocks,
  dateRange,
  daysToShow,
  currentDate,
  businessDate,
  conflicts,
  draggingBooking,
  resizingBooking,
  dragOverCell,
  showDeluxePanel,
  groupColorMap,
  setGroupColorMap,
  groupBookings: deluxeGroupBookings,
  getOccupancyForDate,
  // Handlers
  onCellClick,
  onCellMouseDown,
  onCellMouseEnter,
  dragSelect,
  onDragStart,
  onResizeStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
  onBookingDoubleClick,
  showOccupancyBand = false,
  dailyRates = {},
}) => {
  const { t } = useTranslation();
  const [collapsedTypes, setCollapsedTypes] = useState(() => new Set());

  const toggleType = (type) => {
    setCollapsedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const hasConflict = (roomId, date) => {
    return conflicts.some(c =>
      c.room_id === roomId &&
      date >= new Date(c.overlap_start) &&
      date < new Date(c.overlap_end)
    );
  };

  // Bir rezervasyonun dahil olduğu çakışma kaydını (varsa) döndürür — tooltip
  // metni için kullanılır ("!!" rozeti ve yanıp sönen halkanın açıklaması).
  const getConflictInfo = (roomId, booking) => {
    return conflicts.find(c =>
      c.room_id === roomId &&
      (c.booking1_id === booking.id || c.booking2_id === booking.id)
    );
  };

  const formatConflictRange = (start, end) => {
    try {
      const opts = { day: 'numeric', month: 'short' };
      return `${new Date(start).toLocaleDateString('tr-TR', opts)} – ${new Date(end).toLocaleDateString('tr-TR', opts)}`;
    } catch {
      return '';
    }
  };

  const isGroupBooking = (bookingId) => {
    return (deluxeGroupBookings || []).some(g => g.booking_ids?.includes(bookingId));
  };

  const getGroupInfo = (bookingId) => {
    return (deluxeGroupBookings || []).find(g => g.booking_ids?.includes(bookingId));
  };

  // Rezervasyonları oda bazında tek seferde grupla (iptal/no-show hariç) ve yalnızca
  // görünür tarih aralığıyla kesişenleri tut. Böylece lane hesabı (a) her render'da
  // her oda için tüm bookings'i taramaz, (b) görünmeyen ileri tarihli çakışmalar
  // satır yüksekliğini boş yere şişirmez.
  const rangeStartStr = dateRange.length > 0 ? toDateStringUTC(dateRange[0]) : '';
  const rangeEndStr = dateRange.length > 0
    ? toDateStringUTC(new Date(dateRange[dateRange.length - 1].getTime() + 86400000))
    : '';
  const bookingsByRoom = useMemo(() => {
    const map = new Map();
    if (!rangeStartStr || !rangeEndStr) return map;
    for (const b of bookings) {
      if (!b.room_id || b.status === 'cancelled' || b.status === 'no_show') continue;
      const ci = toDateStringUTC(b.check_in);
      const co = toDateStringUTC(b.check_out);
      if (!(ci < rangeEndStr && co > rangeStartStr)) continue; // görünür aralıkla kesişmiyor
      let arr = map.get(b.room_id);
      if (!arr) { arr = []; map.set(b.room_id, arr); }
      arr.push(b);
    }
    return map;
  }, [bookings, rangeStartStr, rangeEndStr]);

  const getGroupColor = (booking) => {
    if (!booking || !booking.group_booking_id) return '#2563eb';
    const groupId = booking.group_booking_id;
    if (groupColorMap[groupId]) return groupColorMap[groupId];
    const palette = ['#2563eb', '#0891b2', '#7c3aed', '#db2777', '#059669', '#ea580c'];
    let hash = 0;
    for (let i = 0; i < groupId.length; i++) {
      hash = groupId.charCodeAt(i) + ((hash << 5) - hash);
    }
    const idx = Math.abs(hash) % palette.length;
    const color = palette[idx];
    setGroupColorMap(prev => ({ ...prev, [groupId]: color }));
    return color;
  };

  // Group rooms by type
  const groupedRooms = rooms.reduce((acc, room) => {
    const type = room.room_type || 'standard';
    if (!acc[type]) acc[type] = [];
    acc[type].push(room);
    return acc;
  }, {});

  const roomTypeOrder = ['suite', 'deluxe', 'superior', 'standard', 'economy'];
  const sortedTypes = Object.keys(groupedRooms).sort((a, b) => {
    const aIndex = roomTypeOrder.indexOf(a.toLowerCase());
    const bIndex = roomTypeOrder.indexOf(b.toLowerCase());
    if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
    if (aIndex === -1) return 1;
    if (bIndex === -1) return -1;
    return aIndex - bIndex;
  });

  return (
    <div
      className="bg-white rounded-xl border border-slate-200 shadow-sm relative flex flex-col h-full overflow-hidden select-none"
      data-testid="calendar-grid"
      onPointerDown={clearCalendarTextSelection}
    >
      {/* Date Header Row - STICKY */}
      <div className="overflow-auto flex-1">
        <div className="min-w-max pb-12">
          {showOccupancyBand && (
            <OccupancyBand
              dateRange={dateRange}
              daysToShow={daysToShow}
              cellW={CELL_W}
              getOccupancyForDate={getOccupancyForDate}
              roomsCount={Array.isArray(rooms) ? rooms.length : 0}
            />
          )}
          <div className="sticky top-0 z-40 bg-white border-b border-gray-300">
          <div className="flex">
            <div className={`${LABEL_CLS} sticky left-0 z-50 flex-shrink-0 border-r border-slate-200 bg-slate-50`}></div>
            <div className="flex-1 text-center text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500 py-1.5 bg-slate-50">
              {dateRange.length > 0 && dateRange[Math.floor(dateRange.length / 2)].toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' })}
            </div>
          </div>
          <div className="flex bg-white shadow-[0_2px_6px_rgba(15,23,42,0.06)]">
            <div className={`${LABEL_CLS} sticky left-0 z-50 flex-shrink-0 px-3 py-2 border-r border-slate-200 bg-white text-[11px] text-slate-500 font-semibold flex items-end`}>
              <button
                type="button"
                onClick={() => {
                  const allCollapsed = sortedTypes.length > 0 && sortedTypes.every((t) => collapsedTypes.has(t));
                  if (allCollapsed) setCollapsedTypes(new Set());
                  else setCollapsedTypes(new Set(sortedTypes));
                }}
                className="flex items-center gap-0.5 cursor-pointer hover:text-gray-800 select-none"
                data-testid="calendar-collapse-all-btn"
                title={t('cm.pages_calendar_CalendarGrid.tum_oda_tiplerini_ac_kapat')}
              >
                {sortedTypes.length > 0 && sortedTypes.every((t) => collapsedTypes.has(t)) ? (
                  <>
                    <ChevronRight className="w-3 h-3" /> {t('cm.pages_calendar_CalendarGrid.genislet')}
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3 h-3" /> Daralt
                  </>
                )}
              </button>
            </div>
            {dateRange.map((date, idx) => {
              const { dayName, dayNum } = formatDateWithDay(date);
              const weekend = isWeekend(date);
              const today = isToday(date);
              const past = isPastDate(date);
              return (
                <div
                  key={idx}
                  className={`${CELL_CLS} flex-shrink-0 py-2 border-r text-center ${
                    today ? 'bg-blue-100 border-blue-300 shadow-[inset_0_3px_0_#2563eb]' : past ? 'bg-slate-100 border-slate-200' : weekend ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'
                  }`}
                  data-testid={`date-header-${dayNum}`}
                >
                  <div
                    lang="tr"
                    translate="no"
                    title={date.toLocaleDateString('tr-TR', { weekday: 'long' })}
                    className={`notranslate text-[10px] font-bold uppercase tracking-wide ${today ? 'text-blue-700' : past ? 'text-slate-400' : 'text-slate-500'}`}
                  >
                    {dayName}
                  </div>
                  <div className={`text-[18px] font-extrabold leading-tight ${today ? 'text-blue-700' : past ? 'text-slate-400' : 'text-slate-900'}`}>
                    {dayNum}
                  </div>
                </div>
              );
            })}
          </div>
          </div>

          {/* Room Rows */}
          {rooms.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              <CalendarIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>{t('cm.pages_calendar_CalendarGrid.oda_bulunamadi')}</p>
            </div>
          ) : (
            sortedTypes.map((roomType) => {
              const typeRooms = groupedRooms[roomType];
              const unassignedForType = getUnassignedBookingsForType(roomType, bookings, dateRange);

              return (
                <div key={roomType}>
                  {/* Room Type Header */}
                  <div className="bg-gradient-to-r from-slate-100 to-blue-50 border-b border-blue-200" data-testid="room-type-row">
                    <div className="flex">
                      <div className={`${LABEL_CLS} sticky left-0 z-30 flex-shrink-0 px-3 py-2 border-r border-blue-200 bg-slate-100 flex items-center`}>
                        <button
                          type="button"
                          onClick={() => toggleType(roomType)}
                          className="flex items-center gap-1.5 font-extrabold text-[13px] text-slate-900 tracking-tight hover:text-blue-700 select-none"
                          data-testid={`room-type-${roomType}`}
                          title={collapsedTypes.has(roomType) ? 'Aç' : 'Daralt'}
                        >
                          {collapsedTypes.has(roomType) ? (
                            <ChevronRight className="w-3 h-3" />
                          ) : (
                            <ChevronDown className="w-3 h-3" />
                          )}
                          <span>{roomType}</span>
                        </button>
                      </div>
                      {dateRange.map((date, idx) => {
                        const weekend = isWeekend(date);
                        const past = isPastDate(date);
                        // Count assigned bookings for this room type
                        const assignedBookings = bookings.filter(b => {
                          if (b.status === 'cancelled' || b.status === 'checked_out' || b.status === 'no_show') return false;
                          const room = rooms.find(r => r.id === b.room_id);
                          if (!room || (room.room_type || 'standard') !== roomType) return false;
                          return isBookingOnDate(b, date);
                        });
                        // Count unassigned bookings for this room type on this date
                        const rtLower = roomType.toLowerCase();
                        const unassignedOnDate = bookings.filter(b => {
                          if (b.status === 'cancelled' || b.status === 'checked_out' || b.status === 'no_show') return false;
                          if (b.room_id) return false;
                          const bType = (b.room_type || '').toLowerCase();
                          const bTypeId = (b.room_type_id || '').toLowerCase();
                          if (bType !== rtLower && bTypeId !== rtLower) return false;
                          return isBookingOnDate(b, date);
                        });
                        const occupiedCount = assignedBookings.length + unassignedOnDate.length;
                        const totalTypeRooms = typeRooms.length;
                        const isFull = occupiedCount >= totalTypeRooms;
                        const dayKey = toDateStringUTC(date);
                        const configuredRate = dailyRates[`${roomType}|${dayKey}`];
                        const displayRate = configuredRate ?? typeRooms[0]?.base_price ?? 0;

                        return (
                          <div
                            key={idx}
                            className={`${CELL_CLS} flex-shrink-0 px-0.5 py-1 border-r text-center text-[9px] ${
                              past ? 'bg-gray-100/70 border-gray-200' : weekend ? 'bg-blue-100/50 border-blue-200' : 'bg-blue-50/80 border-blue-200'
                            }`}
                          >
                            <div className={`text-[10px] font-bold truncate ${past ? 'text-gray-400' : 'text-gray-800'}`}>
                              {displayRate > 0 ? `${displayRate.toLocaleString('tr-TR')} TL` : '-'}
                            </div>
                            <div className="flex items-center justify-center gap-0.5 mt-0.5">
                              <div className={`w-1.5 h-1.5 rounded-full ${isFull ? 'bg-red-500' : occupiedCount > 0 ? 'bg-amber-500' : 'bg-green-500'}`}></div>
                              <span className={`text-[8px] font-bold ${isFull ? 'text-red-600' : occupiedCount > 0 ? 'text-amber-600' : 'text-green-700'}`}>
                                {occupiedCount}/{totalTypeRooms}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Unassigned bookings stay visually neutral; their cards use
                      the same three lifecycle colors as assigned bookings. */}
                  {unassignedForType.length > 0 && (() => {
                    const { lanes, maxLane } = computeUnassignedLanes(unassignedForType);
                    const rowHeight = (maxLane + 1) * LANE_H + 6;
                    return (
                      <div className="flex border-b border-slate-200 bg-slate-50/30" style={{ contentVisibility: 'auto', containIntrinsicSize: `100% ${rowHeight}px` }}>
                        <div className={`${LABEL_CLS} sticky left-0 z-30 flex-shrink-0 px-3 py-2 border-r border-gray-200 bg-slate-50/80`} style={{ height: `${rowHeight}px` }}>
                          <div className="flex items-center gap-1">
                            <div className="w-2 h-2 bg-slate-400 rounded-full"></div>
                            <div className="font-bold text-[9px] text-slate-700">{t('cm.pages_calendar_CalendarGrid.atanmamis')}</div>
                          </div>
                          <div className="text-[10px] ml-3 text-slate-500">
                            {unassignedForType.length} rez.
                          </div>
                        </div>
                        <div className="flex relative" style={{ width: `${daysToShow * CELL_W}px`, height: `${rowHeight}px` }}>
                          {dateRange.map((date, idx) => {
                            const weekend = isWeekend(date);
                            return (
                              <div
                                key={idx}
                                className={`${CELL_CLS} flex-shrink-0 border-r border-b relative ${
                                  weekend ? 'bg-blue-50/30 border-blue-100' : 'bg-blue-50/10 border-blue-100'
                                } ${isToday(date) ? 'bg-blue-50/40' : ''}`}
                                style={{ height: `${rowHeight}px`, minHeight: `${rowHeight}px` }}
                              />
                            );
                          })}
                          {unassignedForType.map((booking) => {
                            const checkInStr = toDateStringUTC(booking.check_in);
                            const checkOutStr = toDateStringUTC(booking.check_out);
                            const rangeStartStr = dateRange.length > 0 ? toDateStringUTC(dateRange[0]) : '';
                            let startIdx = dateRange.findIndex(d => toDateStringUTC(d) === checkInStr);
                            if (startIdx < 0 && checkInStr < rangeStartStr && checkOutStr > rangeStartStr) startIdx = 0;
                            if (startIdx < 0) return null;
                            const lane = lanes[booking.id] || 0;
                            const visibleEndIdx = dateRange.findIndex(d => toDateStringUTC(d) >= checkOutStr);
                            const endIdx = visibleEndIdx >= 0 ? visibleEndIdx : dateRange.length;
                            const span = Math.max(endIdx - startIdx, 1);
                            const urgency = getUnassignedUrgency(booking);
                            const statusColor = getBookingStatusColor(booking);
                            const fullGuestName = formatGuestName(booking.guest_name) || 'Misafir';
                            const displayGuestName = compactGuestName(fullGuestName, span === 1 ? 10 : 20);
                            return (
                              <div
                                key={booking.id}
                                draggable
                                tabIndex={0}
                                role="button"
                                aria-label={`${fullGuestName}, ${urgency.label}, atanmamış — odaya sürükleyin`}
                                onDragStart={(e) => onDragStart(e, booking)}
                                onDragEnd={onDragEnd}
                                onDoubleClick={() => onBookingDoubleClick(booking)}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onBookingDoubleClick(booking); } }}
                                className="absolute rounded text-[10px] text-white shadow-sm hover:shadow-lg hover:-translate-y-px transition-all cursor-move z-20 border-2 outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
                                style={{
                                  left: `${startIdx * CELL_W + 2}px`,
                                  top: `${lane * LANE_H + 3}px`,
                                  width: `${span * CELL_W - 4}px`,
                                  height: `${LANE_H - 6}px`,
                                  backgroundColor: statusColor.bg,
                                  borderColor: statusColor.border,
                                }}
                                data-testid={`unassigned-booking-${booking.id}`}
                                title={`${fullGuestName} — ${urgency.label} — Odaya sürükleyin`}
                              >
                                <div className="flex h-full overflow-hidden">
                                  <div className="px-1 py-0.5 flex-1 min-w-0 flex items-center gap-1">
                                    <div className="min-w-0 flex-1">
                                      <div className="font-extrabold text-[10px] text-white truncate leading-tight">
                                        {displayGuestName}
                                      </div>
                                    </div>
                                    <span className="sr-only">{urgency.label}</span>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Rooms of this type */}
                  {!collapsedTypes.has(roomType) && typeRooms.map((room) => {
                    const refTodayStr = businessDate || toDateStringUTC(new Date());
                    const isActiveOn = (b, dStr) => {
                      const ci = toDateStringUTC(b.check_in);
                      const co = toDateStringUTC(b.check_out);
                      return dStr >= ci && dStr < co;
                    };
                    // Bu odanın görünür aralıkla kesişen, iptal/no-show olmayan
                    // rezervasyonları (checked_out dahil → turuncu kart). Lane hesabı ile
                    // aynı odadaki çakışanlar üst üste binmek yerine alt alta dizilir.
                    const roomBookings = bookingsByRoom.get(room.id) || [];
                    const { lanes, maxLane } = computeUnassignedLanes(roomBookings);
                    const laneCount = maxLane + 1;
                    const rowHeight = Math.max(CELL_H, laneCount * LANE_BAR_H + 4);
                    const hasBookingToday = roomBookings.some(b => isActiveOn(b, refTodayStr) && b.status !== 'checked_out');
                    const roomBlockedStatus = isBlockedRoomStatus(room.status);
                    // Satır göstergesi nokta rengi, hücre tinti ile aynı önceliği izler:
                    // OOO/OOS (blocked, gri) > bugün dolu (occupied, kırmızı) > boş (yeşil).
                    const roomDotStatus = roomBlockedStatus ? 'blocked' : hasBookingToday ? 'occupied' : 'free';
                    const roomDotColor = roomDotStatus === 'blocked' ? 'bg-slate-400' : roomDotStatus === 'occupied' ? 'bg-red-500' : 'bg-green-500';
                    return (
                      <div key={room.id} className="flex border-b border-slate-200 hover:bg-blue-50/50 transition-colors" data-testid="room-row" style={{ contentVisibility: 'auto', containIntrinsicSize: `100% ${rowHeight}px` }}>
                        <div className={`${LABEL_CLS} sticky left-0 z-30 flex-shrink-0 px-3 py-1 border-r border-slate-200 bg-white flex items-center shadow-[3px_0_8px_rgba(15,23,42,0.05)]`} style={{ height: `${rowHeight}px` }}>
                          <div className="flex items-center gap-2">
                            <div
                              className={`w-2.5 h-2.5 rounded-full ring-2 ring-white shadow-sm ${roomDotColor}`}
                              title={roomDotStatus === 'blocked' ? 'Blok (OOO/OOS)' : roomDotStatus === 'occupied' ? 'Bugün dolu' : 'Boş'}
                              data-testid={`room-status-dot-${roomDotStatus}`}
                            ></div>
                            <div>
                              <div className="font-extrabold text-[14px] leading-tight text-slate-900" data-testid={`room-${room.room_number}`}>{room.room_number}</div>
                              <div className="text-[9px] font-medium text-slate-400 leading-tight">{roomType}</div>
                            </div>
                          </div>
                        </div>
                        <div className="flex relative" style={{ width: `${daysToShow * CELL_W}px`, height: `${rowHeight}px` }}>
                          {/* Arka plan hücreleri: blok, drag-over, tıkla-oluştur, boş gösterge */}
                          {dateRange.map((date, idx) => {
                            const dStr = toDateStringUTC(date);
                            const covered = roomBookings.some(b => isActiveOn(b, dStr) && b.status !== 'checked_out');
                            const roomBlock = getRoomBlockForDate(room.id, date, roomBlocks);
                            const bBlockIsStart = roomBlock && isBlockStart(roomBlock, date);
                            const isDragOver = dragOverCell?.roomId === room.id &&
                              new Date(dragOverCell.date).toDateString() === date.toDateString();
                            const past = isPastDate(date);
                            const blockedForSell = !!roomBlock && roomBlock.allow_sell === false;
                            const invalidDrop = isDragOver && blockedForSell;
                            const canCreate = !covered && !roomBlock && !past;
                            // Dolu/blok/boş hücre tinti — roomOccupancyStatus ile aynı
                            // öncelik (OOO/OOS önde, sonra occupied > blocked > free).
                            // Overlay olarak uygulanır ki past/today/weekend taban tonu,
                            // blok şeridi ve rezervasyon barları üzerine net binsin.
                            const occStatus = cellOccupancyStatus({
                              covered,
                              blocked: !!roomBlock,
                              roomStatus: room.status,
                            });
                            const occTint = getCellOccupancyTint(occStatus);
                            // Tut-surukle cok-gece secimi: yalnizca ayni odadaki bos
                            // hucreler vurgulanir; aradaki dolu/bloklu hucreler haric.
                            const inDragSel = !!dragSelect && dragSelect.roomId === room.id && canCreate && (() => {
                              const lo = dragSelect.startStr <= dragSelect.endStr ? dragSelect.startStr : dragSelect.endStr;
                              const hi = dragSelect.startStr <= dragSelect.endStr ? dragSelect.endStr : dragSelect.startStr;
                              return dStr >= lo && dStr <= hi;
                            })();

                            return (
                              <div
                                key={idx}
                                className={`${CELL_CLS} flex-shrink-0 border-r border-slate-200 relative transition-colors group/cell select-none ${
                                  canCreate ? 'cursor-pointer' : 'cursor-default'
                                } ${
                                  past ? 'bg-slate-100/80' : isToday(date) ? 'bg-blue-100/70 dark:bg-blue-950/70' : isWeekend(date) ? 'bg-amber-50/70 dark:bg-amber-950/70' : 'bg-white hover:bg-blue-50/50'
                                } ${roomBlock ? 'bg-gray-100/60 border-dashed' : ''} ${
                                  inDragSel ? 'bg-indigo-100/70 ring-2 ring-inset ring-indigo-400 z-10' : ''
                                }`}
                                style={{ height: `${rowHeight}px`, minHeight: `${rowHeight}px`, overflow: 'visible' }}
                                onClick={() => !covered && !roomBlock && onCellClick(room.id, date)}
                                onMouseDown={canCreate ? (e) => { if (e.button === 0) { e.preventDefault(); onCellMouseDown?.(room.id, date); } } : undefined}
                                onMouseEnter={canCreate ? () => onCellMouseEnter?.(room.id, date) : undefined}
                                onDragOver={(e) => onDragOver(e, room.id, date)}
                                onDragLeave={onDragLeave}
                                onDrop={(e) => onDrop(e, room.id, date)}
                                data-testid={`calendar-cell-${room.room_number}-${toDateStringUTC(date)}`}
                                title={roomBlock ? `${roomBlock.type.toUpperCase()}: ${roomBlock.reason}` : ''}
                              >
                                {/* Dolu/blok/boş doluluk tinti (en alt katman) */}
                                {occTint && (
                                  <div
                                    className={`absolute inset-0 pointer-events-none ${occTint}`}
                                    aria-hidden="true"
                                    data-testid={`cell-occupancy-${occStatus}`}
                                  />
                                )}

                                {/* Room Block Indicator */}
                                {bBlockIsStart && roomBlock && (
                                  <div
                                    className={`absolute top-0 left-0 h-full opacity-60 border-2 ${
                                      roomBlock.type === 'out_of_order' ? 'bg-red-600 border-red-700' :
                                      roomBlock.type === 'out_of_service' ? 'bg-amber-500 border-amber-600' :
                                      'bg-yellow-600 border-yellow-700'
                                    }`}
                                    style={{
                                      width: `${calculateBlockSpan(roomBlock, currentDate, daysToShow) * CELL_W - 4}px`,
                                      zIndex: 5
                                    }}
                                    title={`${roomBlock.type.replace('_', ' ').toUpperCase()}: ${roomBlock.reason}\n${roomBlock.start_date} - ${roomBlock.end_date || 'Open-ended'}`}
                                  >
                                    <div className="p-0.5 text-white text-[8px] font-bold">
                                      {roomBlock.type === 'out_of_order' ? 'OOO' :
                                       roomBlock.type === 'out_of_service' ? 'OOS' : 'MNT'}
                                    </div>
                                  </div>
                                )}

                                {/* Drop target preview (visual only) — valid=emerald, invalid=soft red */}
                                {isDragOver && (
                                  <div
                                    data-testid="calendar-drop-target"
                                    aria-hidden="true"
                                    className={`absolute inset-0 z-10 pointer-events-none rounded-sm ${
                                      invalidDrop
                                        ? 'bg-red-100/50 ring-2 ring-inset ring-red-400'
                                        : 'bg-emerald-100/50 ring-2 ring-inset ring-emerald-400'
                                    }`}
                                  />
                                )}

                                {/* Empty cell hover affordance — only on valid, non-past cells */}
                                {canCreate && (
                                  <div
                                    className="absolute inset-0 flex items-center justify-center opacity-0 group-hover/cell:opacity-100 transition-opacity pointer-events-none"
                                    data-testid="calendar-empty-cell"
                                    aria-hidden="true"
                                  >
                                    <span
                                      data-testid="reservation-card-hover-action"
                                      className="flex items-center gap-0.5 max-w-full px-1.5 h-5 rounded-full bg-amber-100 text-amber-700 ring-1 ring-amber-300 shadow-sm text-[9px] font-semibold leading-none"
                                      title="Yeni rezervasyon"
                                    >
                                      <Plus className="w-3 h-3 shrink-0" />
                                      <span className="truncate">Yeni</span>
                                    </span>
                                  </div>
                                )}
                              </div>
                            );
                          })}

                          {/* Rezervasyon barları (overlay) — lane'lere dizilir, aynı odadaki
                              çakışanlar asla üst üste binmez */}
                          {roomBookings.map((booking) => {
                            const checkInStr = toDateStringUTC(booking.check_in);
                            const checkOutStr = toDateStringUTC(booking.check_out);
                            let startIdx = dateRange.findIndex(d => toDateStringUTC(d) === checkInStr);
                            // Görünür aralıktan önce başlayıp aralık içine taşan rezervasyonu
                            // ilk kolona kenetle (eskiden böyleleri hiç görünmüyordu).
                            if (startIdx < 0 && checkInStr < rangeStartStr && checkOutStr > rangeStartStr) startIdx = 0;
                            if (startIdx < 0) return null;
                            const span = calculateBookingSpan(booking, currentDate, daysToShow);
                            if (span <= 0) return null;
                            const lane = lanes[booking.id] || 0;
                            const statusColor = getBookingStatusColor(booking, refTodayStr);
                            const conflictInfo = getConflictInfo(room.id, booking);
                            const arrivalInView = startIdx >= 0 && checkInStr === toDateStringUTC(dateRange[startIdx]);
                            const fullGuestName = formatGuestName(booking.guest_name) || 'Misafir';
                            const conflictTitle = conflictInfo
                              ? `⚠ Çakışma: Bu oda ${formatConflictRange(conflictInfo.overlap_start, conflictInfo.overlap_end)} tarihlerinde iki rezervasyona sahip (${conflictInfo.guest1 || 'Misafir'} ↔ ${conflictInfo.guest2 || 'Misafir'}). Lütfen birini başka odaya taşıyın.`
                              : fullGuestName;
                            const isDragging = draggingBooking?.id === booking.id;
                            const isResizing = resizingBooking?.id === booking.id;
                            const resizeAllowed = !['checked_out', 'cancelled', 'no_show'].includes(String(booking.status || '').toLowerCase())
                              && checkOutStr <= rangeEndStr;
                            const paxCount = (booking.adults || 0) + (booking.children || 0);
                            const fmtCardDate = (d) => { try { return new Date(d).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' }); } catch { return ''; } };
                            const displayGuestName = compactGuestName(fullGuestName, span === 1 ? 10 : span === 2 ? 18 : 40);
                            const cardAria = `${fullGuestName}, ${getSourceColor(booking).label}${paxCount ? `, ${paxCount} kişi` : ''}, ${fmtCardDate(booking.check_in)} – ${fmtCardDate(booking.check_out)}`;
                            return (
                              <div
                                key={booking.id}
                                draggable
                                tabIndex={0}
                                role="button"
                                aria-label={cardAria}
                                onDragStart={(e) => onDragStart(e, booking)}
                                onDragEnd={onDragEnd}
                                onDoubleClick={() => onBookingDoubleClick(booking)}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onBookingDoubleClick(booking); } }}
                                className={`absolute rounded-lg text-white text-[10px] transition-all cursor-move z-20 group outline-none border border-white/25 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 ${
                                  isDragging || isResizing
                                    ? 'opacity-90 ring-2 ring-blue-300 shadow-xl scale-[1.02] z-30'
                                    : 'shadow-[0_2px_5px_rgba(15,23,42,0.24)] hover:shadow-lg hover:-translate-y-px hover:z-30'
                                } ${isResizing ? 'pointer-events-none' : ''} ${conflictInfo ? 'ring-2 ring-red-500 animate-pulse' : ''} ${showDeluxePanel && isGroupBooking(booking.id) ? 'ring-2 ring-amber-400' : ''}`}
                                style={{
                                  left: `${startIdx * CELL_W + 2}px`,
                                  top: `${lane * LANE_BAR_H + 2}px`,
                                  width: `${span * CELL_W - 4}px`,
                                  height: `${BOOKING_H}px`,
                                  backgroundColor: statusColor.bg,
                                  borderLeft: `4px solid ${statusColor.border}`,
                                }}
                                data-testid={isDragging ? 'reservation-card-dragging' : `booking-bar-${booking.id}`}
                                title={conflictTitle}
                              >
                                <div className="px-2 py-1 relative overflow-hidden" style={{ height: `${BOOKING_H}px` }}>
                                  <div className="font-extrabold text-[12px] truncate pr-4 text-white leading-tight drop-shadow-sm">
                                    {displayGuestName}
                                  </div>
                                  <div className="text-[9px] text-white/90 truncate flex items-center gap-1 leading-tight mt-0.5">
                                    <span className="font-semibold">{getSourceColor(booking).label}</span>
                                    {(booking.adults || booking.children) ? <span className="opacity-80">· {(booking.adults || 0) + (booking.children || 0)} ks</span> : null}
                                  </div>
                                  <div className="absolute top-0.5 right-0.5 flex flex-col space-y-0.5 items-end">
                                    {showDeluxePanel && isGroupBooking(booking.id) && (
                                      <div className="bg-gradient-to-r from-amber-500 to-amber-600 text-white text-[7px] font-bold px-0.5 py-0 rounded" title={`Group: ${getGroupInfo(booking.id)?.company_name}`}>
                                        G
                                      </div>
                                    )}
                                    {arrivalInView && (
                                      <div className="flex space-x-0.5">
                                        <div className="bg-white text-green-600 rounded-full w-3.5 h-3.5 flex items-center justify-center text-[8px] font-bold" title="Giriş günü">A</div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                                {conflictInfo && (
                                  <div
                                    className="absolute top-0 right-0 bg-red-600 text-white text-[7px] px-0.5 rounded-bl font-bold animate-pulse"
                                    title={conflictTitle}
                                  >
                                    !!
                                  </div>
                                )}
                                {resizeAllowed && (
                                  <div
                                    draggable
                                    role="separator"
                                    aria-orientation="vertical"
                                    aria-label={`${fullGuestName} konaklama süresini değiştir`}
                                    title="Konaklamayı uzat veya kısalt"
                                    data-testid={`booking-resize-handle-${booking.id}`}
                                    onDragStart={(e) => { e.stopPropagation(); onResizeStart?.(e, booking); }}
                                    onDragEnd={(e) => { e.stopPropagation(); onDragEnd?.(); }}
                                    onClick={(e) => e.stopPropagation()}
                                    onDoubleClick={(e) => e.stopPropagation()}
                                    className="absolute right-0 top-0 z-40 h-full w-5 cursor-ew-resize touch-none rounded-r-lg border-l border-white/50 bg-slate-950/30 opacity-90 hover:bg-slate-950/55 after:absolute after:right-2 after:top-1/2 after:h-6 after:w-1 after:-translate-y-1/2 after:rounded after:border-x after:border-white/90"
                                  />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};

export default CalendarGrid;
