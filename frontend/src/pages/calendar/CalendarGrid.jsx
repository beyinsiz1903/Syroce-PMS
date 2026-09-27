import React, { useEffect, useState, useMemo, useRef } from "react";
import { Calendar as CalendarIcon, Plus, ChevronDown, ChevronRight, Wrench, ExternalLink } from "lucide-react";
import {
  toDateStringUTC, checkoutAfterCalendarNight, isBookingOnDate, isBookingStart, isWeekend, isToday, isPastDate,
  formatDateWithDay, getBookingForRoomOnDate, getRoomBlockForDate,
  isBlockStart, calculateBlockSpan, calculateBookingSpan,
  getSourceColor,
  getUnassignedBookingsForType, computeUnassignedLanes,
  getUnassignedUrgency,
  isRoomBlockedForSaleOnDate, getRoomTypeCapacityForDate, cellOccupancyStatus, getCellOccupancyTint,
} from "./calendarHelpers";
import { useTranslation } from 'react-i18next';
import OccupancyBand from "./OccupancyBand";
import { compactGuestName, formatGuestName } from './roomTypeMatching';
import { CALENDAR_DAY_WIDTH } from './bookingDragPlacement';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';

// A full guest name must remain legible even for a one-night stay.  A slightly
// wider day column with a two-line title is a better trade-off than anonymous
// looking cards; narrower screens keep the existing horizontal scroll.
const CELL_W = CALENDAR_DAY_WIDTH;
const CELL_CLS = 'w-[104px]';
const LABEL_CLS = 'w-52';
const CELL_H = 60;
const BOOKING_H = 54;
const LANE_H = 40;
const LANE_BAR_H = 58;

const cardDateFormatter = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' });

const formatCardDate = (value) => {
  try {
    return cardDateFormatter.format(new Date(value));
  } catch {
    return '';
  }
};

export const getReservationCardPresentation = (booking) => {
  const guestName = formatGuestName(booking?.guest_name) || 'Misafir';
  const source = getSourceColor(booking || {});
  const paxCount = Number(booking?.adults || 0) + Number(booking?.children || 0);
  const normalizedStatus = String(booking?.status || '').toLowerCase();
  const statusLabel = normalizedStatus === 'checked_in'
    ? 'Otelde'
    : normalizedStatus === 'checked_out'
      ? 'Çıkış yapıldı'
      : 'Giriş bekliyor';
  const stayRange = `${formatCardDate(booking?.check_in)} – ${formatCardDate(booking?.check_out)}`;

  return {
    guestName,
    sourceLabel: source.label,
    paxCount,
    statusLabel,
    stayRange,
    ariaLabel: `${guestName}, ${statusLabel}, ${source.label}${paxCount ? `, ${paxCount} kişi` : ''}, ${stayRange}`,
  };
};

export const getReservationCardSurface = (booking) => {
  const status = String(booking?.status || '').toLowerCase();
  if (status === 'checked_in') return { background: '#ecfdf5', border: '#10b981', text: '#064e3b', muted: '#047857' };
  if (status === 'checked_out') return { background: '#fff1f2', border: '#f43f5e', text: '#881337', muted: '#be123c' };
  return { background: '#eff6ff', border: '#3b82f6', text: '#172554', muted: '#1d4ed8' };
};

export const clearCalendarTextSelection = () => {
  window.getSelection?.()?.removeAllRanges();
};

export const normalizeRoomTypeKey = (value) => String(value || 'standard').trim().toLocaleLowerCase('tr-TR');

export const formatRoomTypeLabel = (value) => {
  const normalized = normalizeRoomTypeKey(value);
  return normalized.charAt(0).toLocaleUpperCase('tr-TR') + normalized.slice(1);
};

export const formatCalendarMonthRange = (dateRange) => {
  if (!dateRange?.length) return '';
  const first = dateRange[0];
  const last = dateRange[dateRange.length - 1];
  const month = (date) => date.toLocaleDateString('tr-TR', { month: 'long' }).toLocaleUpperCase('tr-TR');
  const firstMonth = month(first);
  const lastMonth = month(last);
  const firstYear = first.getFullYear();
  const lastYear = last.getFullYear();
  if (firstMonth === lastMonth && firstYear === lastYear) return `${firstMonth} ${firstYear}`;
  if (firstYear === lastYear) return `${firstMonth} — ${lastMonth} ${lastYear}`;
  return `${firstMonth} ${firstYear} — ${lastMonth} ${lastYear}`;
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
  onResizePointerStart,
  onResizePointerCommit,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
  onBookingClick,
  onBookingDoubleClick,
  onOpenRoomBlock,
  showOccupancyBand = false,
  dailyRates = {},
}) => {
  const { t } = useTranslation();
  const [collapsedTypes, setCollapsedTypes] = useState(() => new Set());
  const [contextMenu, setContextMenu] = useState(null);
  const [, setPointerResize] = useState(null);
  const pointerResizeRef = useRef(null);
  const suppressCardClickUntilRef = useRef(0);
  const bookingClickTimerRef = useRef(null);

  const startBookingDrag = (event, booking, date) => {
    suppressCardClickUntilRef.current = Date.now() + 350;
    onDragStart(event, booking, date);
  };

  const openBookingQuickPanel = (booking) => {
    if (Date.now() < suppressCardClickUntilRef.current) return;
    window.clearTimeout(bookingClickTimerRef.current);
    bookingClickTimerRef.current = window.setTimeout(() => onBookingClick?.(booking), 220);
  };

  const openBookingWorkspace = (event, booking) => {
    event.stopPropagation();
    window.clearTimeout(bookingClickTimerRef.current);
    bookingClickTimerRef.current = null;
    onBookingDoubleClick(booking);
  };

  const pointerDate = (event) => {
    const target = document.elementFromPoint?.(event.clientX, event.clientY);
    const cell = target?.closest?.('[data-calendar-date]');
    return cell?.dataset.calendarDate || '';
  };

  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    return () => { window.removeEventListener('click', close); window.removeEventListener('scroll', close, true); };
  }, []);

  useEffect(() => () => window.clearTimeout(bookingClickTimerRef.current), []);

  const openContextMenu = (event, payload) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      ...payload,
      x: Math.min(event.clientX, window.innerWidth - 220),
      y: Math.min(event.clientY, window.innerHeight - 180),
    });
  };

  const completePointerResize = (event) => {
    const activeResize = pointerResizeRef.current;
    if (!activeResize) return;
    const targetDate = pointerDate(event) || activeResize.targetDate;
    const { booking } = activeResize;
    pointerResizeRef.current = null;
    setPointerResize(null);
    if (targetDate) onResizePointerCommit?.(booking, new Date(`${targetDate}T00:00:00Z`));
  };

  const updatePointerResize = (event) => {
    const activeResize = pointerResizeRef.current;
    if (!activeResize) return;
    const targetDate = pointerDate(event);
    if (!targetDate || targetDate === activeResize.targetDate) return;

    // Do not make React re-render every room and day while the pointer moves.
    // The board has hundreds of cells; mutating just the active card makes the
    // resize preview follow the cursor immediately, like HotelRunner.
    activeResize.targetDate = targetDate;
    const previewCheckOut = checkoutAfterCalendarNight(targetDate);
    const span = calculateBookingSpan(
      { ...activeResize.booking, check_out: previewCheckOut },
      currentDate,
      daysToShow,
    );
    const card = document.querySelector(`[data-booking-id="${String(activeResize.booking.id)}"]`);
    if (card && span > 0) card.style.width = `${span * CELL_W - 4}px`;
  };

  const cancelPointerResize = () => {
    pointerResizeRef.current = null;
    setPointerResize(null);
  };

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

  // Text, source and lifecycle labels are shared by assigned and unassigned
  // cards. Calculate them once per booking update instead of on every room
  // row and interaction render.
  const bookingPresentationById = useMemo(() => {
    const map = new Map();
    bookings.forEach((booking) => map.set(booking.id, getReservationCardPresentation(booking)));
    return map;
  }, [bookings]);

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

  // Build room lookups once. The room-type summary used to scan every booking
  // and every room for every visible day, which made 14/30-day navigation feel
  // heavier as the property filled up.
  const { groupedRooms, roomById } = useMemo(() => {
    const groups = {};
    const byId = new Map();
    rooms.forEach((room) => {
      const type = normalizeRoomTypeKey(room.room_type);
      if (!groups[type]) groups[type] = [];
      groups[type].push(room);
      byId.set(room.id, room);
    });
    return { groupedRooms: groups, roomById: byId };
  }, [rooms]);

  const occupiedByTypeAndDate = useMemo(() => {
    const counts = new Map();
    bookings.forEach((booking) => {
      if (['cancelled', 'checked_out', 'no_show'].includes(booking.status)) return;
      const room = booking.room_id ? roomById.get(booking.room_id) : null;
      const type = normalizeRoomTypeKey(room?.room_type || booking.room_type || booking.room_type_id || '');
      if (!type) return;
      dateRange.forEach((date) => {
        if (!isBookingOnDate(booking, date)) return;
        const key = `${type}|${toDateStringUTC(date)}`;
        counts.set(key, (counts.get(key) || 0) + 1);
      });
    });
    return counts;
  }, [bookings, dateRange, roomById]);

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
      className="relative flex h-full flex-col overflow-hidden border-y border-slate-200 bg-white shadow-[0_8px_30px_rgba(15,23,42,0.05)] select-none"
      data-testid="calendar-grid"
      onPointerDown={clearCalendarTextSelection}
      onPointerMove={updatePointerResize}
      onPointerUp={completePointerResize}
      onPointerCancel={cancelPointerResize}
    >
      {/* Date Header Row - STICKY */}
      <div className="overflow-auto flex-1">
        <div className="min-w-max">
          {showOccupancyBand && (
            <OccupancyBand
              dateRange={dateRange}
              daysToShow={daysToShow}
              cellW={CELL_W}
              getOccupancyForDate={getOccupancyForDate}
              roomsCount={Array.isArray(rooms) ? rooms.length : 0}
            />
          )}
          <div className="sticky top-0 z-40 bg-white border-b border-slate-300">
          <div className="flex">
            <div className={`${LABEL_CLS} sticky left-0 z-50 flex-shrink-0 border-r border-slate-300 bg-slate-50`}></div>
            <div className="flex-1 text-center text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500 py-1.5 bg-slate-50">
              {formatCalendarMonthRange(dateRange)}
            </div>
          </div>
          <div className="flex bg-white shadow-[0_2px_6px_rgba(15,23,42,0.06)]">
            <div className={`${LABEL_CLS} sticky left-0 z-50 flex-shrink-0 px-3 py-2 border-r border-slate-300 bg-white text-[11px] text-slate-500 font-semibold flex items-end`}>
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
                  className={`${CELL_CLS} flex-shrink-0 py-1.5 border-r text-center ${
                    today ? 'bg-blue-50 border-blue-400 shadow-[inset_0_3px_0_#2563eb]' : past || weekend ? 'bg-slate-50 border-slate-300' : 'bg-white border-slate-300'
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
                  <div className={`text-[17px] font-extrabold leading-tight ${today ? 'text-blue-700' : past ? 'text-slate-400' : 'text-slate-900'}`}>
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
                  <div className="border-y border-slate-200 bg-slate-50" data-testid="room-type-row">
                    <div className="flex">
                      <div className={`${LABEL_CLS} sticky left-0 z-30 flex-shrink-0 px-3 py-1.5 border-r border-slate-300 bg-slate-50 flex items-center`}>
                        <button
                          type="button"
                          onClick={() => toggleType(roomType)}
                          className="flex items-center gap-1.5 font-extrabold text-[13px] text-slate-900 tracking-tight transition-colors hover:text-blue-700 select-none"
                          data-testid={`room-type-${roomType}`}
                          title={collapsedTypes.has(roomType) ? 'Aç' : 'Daralt'}
                        >
                          {collapsedTypes.has(roomType) ? (
                            <ChevronRight className="w-3 h-3" />
                          ) : (
                            <ChevronDown className="w-3 h-3" />
                          )}
                          <span>{formatRoomTypeLabel(roomType)}</span>
                        </button>
                      </div>
                      {dateRange.map((date, idx) => {
                        const weekend = isWeekend(date);
                        const past = isPastDate(date);
                        const dayKey = toDateStringUTC(date);
                        const occupiedCount = occupiedByTypeAndDate.get(`${roomType.toLowerCase()}|${dayKey}`) || 0;
                        const capacity = getRoomTypeCapacityForDate(typeRooms, date, roomBlocks);
                        const totalTypeRooms = capacity.sellable;
                        const isFull = occupiedCount >= totalTypeRooms;
                        const sourceRoomType = typeRooms[0]?.room_type || roomType;
                        const configuredRate = dailyRates[`${sourceRoomType}|${dayKey}`] ?? dailyRates[`${roomType}|${dayKey}`];
                        const displayRate = configuredRate ?? typeRooms[0]?.base_price ?? 0;

                        return (
                          <div
                            key={idx}
                          className={`${CELL_CLS} flex-shrink-0 px-0.5 py-1 border-r text-center text-[9px] ${
                              past || weekend ? 'bg-slate-100 border-slate-300' : 'bg-slate-50 border-slate-300'
                            }`}
                          >
                            <div className={`text-[10px] font-bold truncate ${past ? 'text-gray-400' : 'text-gray-800'}`}>
                              {displayRate > 0 ? formatCurrency(displayRate, typeRooms[0]?.currency || cachedTenantCurrency(), { decimals: 0 }) : '-'}
                            </div>
                            <div className="flex items-center justify-center gap-0.5 mt-0.5"
                              title={`${occupiedCount} rezervasyon / ${totalTypeRooms} satılabilir oda · ${capacity.blocked} bloklu · ${capacity.total} toplam`}
                            >
                              <div className={`w-1.5 h-1.5 rounded-full ${isFull ? 'bg-red-500' : occupiedCount > 0 ? 'bg-amber-500' : 'bg-green-500'}`}></div>
                              <span className={`text-[8px] font-bold ${isFull ? 'text-red-600' : occupiedCount > 0 ? 'text-amber-600' : 'text-green-700'}`}>
                                {occupiedCount}/{totalTypeRooms}
                              </span>
                            </div>
                            {capacity.blocked > 0 && (
                              <div className="text-[9px] font-semibold text-slate-600">{capacity.blocked} bloklu</div>
                            )}
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
                      <div className="flex border-b border-slate-300 bg-slate-50/30" style={{ contentVisibility: 'auto', containIntrinsicSize: `100% ${rowHeight}px` }}>
                        <div className={`${LABEL_CLS} sticky left-0 z-30 flex-shrink-0 px-3 py-2 border-r border-slate-300 bg-slate-50/80`} style={{ height: `${rowHeight}px` }}>
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
                                  weekend ? 'bg-blue-50/30 border-blue-200' : 'bg-blue-50/10 border-blue-200'
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
                            const cardSurface = getReservationCardSurface(booking);
                            const presentation = bookingPresentationById.get(booking.id) || getReservationCardPresentation(booking);
                            const fullGuestName = presentation.guestName;
                            const displayGuestName = compactGuestName(fullGuestName, span === 1 ? 10 : 20);
                            return (
                              <div
                                key={booking.id}
                                draggable
                                tabIndex={0}
                                role="button"
                                aria-label={`${fullGuestName}, ${urgency.label}, atanmamış — odaya sürükleyin`}
                                onDragStart={(e) => startBookingDrag(e, booking, dateRange[startIdx])}
                                onDragEnd={onDragEnd}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openBookingQuickPanel(booking);
                                }}
                                onDoubleClick={(e) => openBookingWorkspace(e, booking)}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openBookingQuickPanel(booking); } }}
                                className="absolute transform-gpu rounded-lg text-[10px] shadow-sm hover:shadow-lg hover:-translate-y-px transition-[transform,box-shadow,opacity] duration-150 cursor-move z-20 border outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
                                style={{
                                  left: `${startIdx * CELL_W + 2}px`,
                                  top: `${lane * LANE_H + 3}px`,
                                  width: `${span * CELL_W - 4}px`,
                                  height: `${LANE_H - 6}px`,
                                  backgroundColor: cardSurface.background,
                                  borderColor: `${cardSurface.border}66`,
                                  borderLeft: `4px solid ${cardSurface.border}`,
                                }}
                                data-testid={`unassigned-booking-${booking.id}`}
                                title={`${fullGuestName} — ${urgency.label} — Odaya sürükleyin`}
                              >
                                <div className="flex h-full overflow-hidden">
                                  <div className="px-2 py-1 flex-1 min-w-0 flex items-center gap-1.5">
                                    <span className="h-1.5 w-1.5 shrink-0 rounded-full shadow-sm" style={{ backgroundColor: cardSurface.border }} aria-hidden="true" />
                                    <div className="min-w-0 flex-1">
                                      <div className="font-extrabold text-[10px] truncate leading-tight" style={{ color: cardSurface.text }}>
                                        {displayGuestName}
                                      </div>
                                      {span > 1 && <div className="truncate text-[8px] font-medium" style={{ color: cardSurface.muted }}>Oda bekliyor · {presentation.sourceLabel}</div>}
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
                    const roomBlockedStatus = isRoomBlockedForSaleOnDate(room, refTodayStr, roomBlocks);
                    // Satır göstergesi nokta rengi, hücre tinti ile aynı önceliği izler:
                    // OOO/OOS (blocked, gri) > bugün dolu (occupied, kırmızı) > boş (yeşil).
                    const roomDotStatus = roomBlockedStatus ? 'blocked' : hasBookingToday ? 'occupied' : 'free';
                    const roomDotColor = roomDotStatus === 'blocked' ? 'bg-slate-400' : roomDotStatus === 'occupied' ? 'bg-red-500' : 'bg-green-500';
                    return (
                      <div key={room.id} className={`flex border-b border-slate-300 ${draggingBooking ? '' : 'hover:bg-slate-50/70 transition-colors'}`} data-testid="room-row" style={{ contentVisibility: 'auto', containIntrinsicSize: `100% ${rowHeight}px` }}>
                        <div className={`${LABEL_CLS} sticky left-0 z-30 flex-shrink-0 px-4 py-1 border-r border-slate-300 bg-white flex items-center`} style={{ height: `${rowHeight}px` }}>
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
                            const past = isPastDate(date);
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
                            // HotelRunner benzeri nötr oda-board görünümü için boş
                            // odalar beyaz kalır; yalnız dolu/bloklu hücre vurgulanır.
                            const occTint = occStatus === 'free' ? '' : getCellOccupancyTint(occStatus);
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
                                className={`${CELL_CLS} flex-shrink-0 border-r border-slate-300 relative transition-colors group/cell select-none ${
                                  canCreate ? 'cursor-pointer' : 'cursor-default'
                                } ${
                                  past ? 'bg-slate-50' : isToday(date) ? 'bg-blue-50/70 dark:bg-blue-950/70' : isWeekend(date) ? 'bg-slate-50 dark:bg-slate-900/40' : draggingBooking ? 'bg-white' : 'bg-white hover:bg-slate-50/70'
                                } ${roomBlock ? 'bg-gray-100/60 border-dashed' : ''} ${
                                  inDragSel ? 'bg-indigo-100/70 ring-2 ring-inset ring-indigo-400 z-10' : ''
                                }`}
                                style={{ height: `${rowHeight}px`, minHeight: `${rowHeight}px`, overflow: 'visible' }}
                                onClick={() => !covered && !roomBlock && onCellClick(room.id, date)}
                                onContextMenu={(event) => openContextMenu(event, { kind: 'cell', room, date, covered, roomBlock })}
                                onMouseDown={canCreate ? (e) => { if (e.button === 0) { e.preventDefault(); onCellMouseDown?.(room.id, date); } } : undefined}
                                onMouseEnter={canCreate ? () => onCellMouseEnter?.(room.id, date) : undefined}
                                onDragOver={(e) => onDragOver(e, room.id, date)}
                                onDragLeave={onDragLeave}
                                onDrop={(e) => onDrop(e, room.id, date)}
                                data-calendar-date={dStr}
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

                                {/* Empty cell hover affordance — only on valid, non-past cells */}
                                {canCreate && !draggingBooking && (
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
                            const cardSurface = getReservationCardSurface(booking);
                            const conflictInfo = getConflictInfo(room.id, booking);
                            const arrivalInView = startIdx >= 0 && checkInStr === toDateStringUTC(dateRange[startIdx]);
                            const presentation = bookingPresentationById.get(booking.id) || getReservationCardPresentation(booking);
                            const fullGuestName = presentation.guestName;
                            const conflictTitle = conflictInfo
                              ? `⚠ Çakışma: Bu oda ${formatConflictRange(conflictInfo.overlap_start, conflictInfo.overlap_end)} tarihlerinde iki rezervasyona sahip (${conflictInfo.guest1 || 'Misafir'} ↔ ${conflictInfo.guest2 || 'Misafir'}). Lütfen birini başka odaya taşıyın.`
                              : fullGuestName;
                            const isDragging = draggingBooking?.id === booking.id;
                            const isResizing = resizingBooking?.id === booking.id;
                            const previewSpan = span;
                            const resizeAllowed = !['checked_out', 'cancelled', 'no_show'].includes(String(booking.status || '').toLowerCase())
                              && checkOutStr <= rangeEndStr;
                            const displayGuestName = fullGuestName;
                            return (
                              <div
                                key={booking.id}
                                draggable
                                tabIndex={0}
                                role="button"
                                aria-label={presentation.ariaLabel}
                                onDragStart={(e) => startBookingDrag(e, booking, dateRange[startIdx])}
                                onDragEnd={onDragEnd}
                                // Reservation cards sit above the date cells.  Without their
                                // own drop handlers, dropping directly on an occupied card never
                                // reaches the underlying cell, so an intended room swap appears
                                // to do nothing.
                                onDragOver={(e) => {
                                  e.stopPropagation();
                                  onDragOver(e, room.id, dateRange[startIdx]);
                                }}
                                onDragLeave={(e) => {
                                  e.stopPropagation();
                                  onDragLeave(e);
                                }}
                                onDrop={(e) => {
                                  // The card sits inside a calendar cell.  Do not let the
                                  // same drop bubble to that cell: the second handler does
                                  // not know the target booking and would turn a swap into a
                                  // regular (and correctly rejected) room move.
                                  e.stopPropagation();
                                  onDrop(e, room.id, dateRange[startIdx], booking.id);
                                }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openBookingQuickPanel(booking);
                                }}
                                onDoubleClick={(e) => openBookingWorkspace(e, booking)}
                                onContextMenu={(event) => openContextMenu(event, { kind: 'booking', room, booking })}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openBookingQuickPanel(booking); } }}
                                className={`absolute transform-gpu overflow-hidden rounded-lg text-[10px] cursor-move z-20 group outline-none border transition-[transform,box-shadow,opacity] duration-150 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 ${
                                  isDragging || isResizing
                                    ? 'opacity-40 scale-[0.985] shadow-sm z-30'
                                    : 'shadow-[0_2px_6px_rgba(15,23,42,0.2)] hover:z-30 hover:-translate-y-px hover:shadow-[0_8px_18px_rgba(15,23,42,0.25)]'
                                } ${isResizing ? 'pointer-events-none' : ''} ${conflictInfo ? 'ring-2 ring-red-500 animate-pulse' : ''} ${showDeluxePanel && isGroupBooking(booking.id) ? 'ring-2 ring-amber-400' : ''}`}
                                style={{
                                  left: `${startIdx * CELL_W + 2}px`,
                                  top: `${lane * LANE_BAR_H + 2}px`,
                                  width: `${previewSpan * CELL_W - 4}px`,
                                  height: `${BOOKING_H}px`,
                                  backgroundColor: cardSurface.background,
                                  borderColor: `${cardSurface.border}55`,
                                  borderLeft: `4px solid ${cardSurface.border}`,
                                }}
                                data-booking-id={booking.id}
                                data-testid={isDragging ? 'reservation-card-dragging' : `booking-bar-${booking.id}`}
                                title={conflictTitle}
                              >
                                <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/80" aria-hidden="true" />
                                <div className="px-2 py-1.5 pr-6 relative overflow-hidden" style={{ height: `${BOOKING_H}px` }}>
                                  <div className="font-extrabold text-[12px] leading-[13px] whitespace-normal break-words max-h-[26px] overflow-hidden" style={{ color: cardSurface.text }}>
                                    {displayGuestName}
                                  </div>
                                  <div className="text-[9px] truncate flex items-center gap-1 leading-tight mt-1" style={{ color: cardSurface.muted }}>
                                    <span className="h-1.5 w-1.5 shrink-0 rounded-full shadow-sm" style={{ backgroundColor: cardSurface.border }} aria-hidden="true" />
                                    <span className="font-semibold truncate">{presentation.sourceLabel}</span>
                                    {presentation.paxCount ? <span className="shrink-0 opacity-80">· {presentation.paxCount} kişi</span> : null}
                                    {span > 1 && <span className="ml-auto truncate rounded-full bg-white/70 px-1.5 py-0.5 text-[8px] font-semibold shadow-sm ring-1 ring-black/5">{presentation.statusLabel}</span>}
                                  </div>
                                  <div className="absolute top-0.5 right-0.5 flex flex-col space-y-0.5 items-end">
                                    {showDeluxePanel && isGroupBooking(booking.id) && (
                                      <div className="bg-gradient-to-r from-amber-500 to-amber-600 text-white text-[7px] font-bold px-0.5 py-0 rounded" title={`Group: ${getGroupInfo(booking.id)?.company_name}`}>
                                        G
                                      </div>
                                    )}
                                    {arrivalInView && (
                                      <div className="h-2 w-2 rounded-full border border-white bg-blue-500 shadow-sm" title="Giriş günü" aria-label="Giriş günü" />
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
                                    onPointerDown={(e) => {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      e.currentTarget.setPointerCapture?.(e.pointerId);
                                      pointerResizeRef.current = { booking, targetDate: '' };
                                      setPointerResize({ id: booking.id });
                                      onResizePointerStart?.(booking);
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                    onDoubleClick={(e) => e.stopPropagation()}
                                    className="absolute right-0 top-0 z-40 h-full w-4 cursor-ew-resize touch-none rounded-r-lg border-l border-slate-300/50 bg-transparent opacity-40 transition-colors hover:bg-slate-900/10 hover:opacity-100 focus-visible:bg-slate-900/10 focus-visible:opacity-100 after:absolute after:right-1.5 after:top-1/2 after:h-5 after:w-0.5 after:-translate-y-1/2 after:rounded-full after:bg-slate-500/70"
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
      {contextMenu && (
        <div
          role="menu"
          aria-label="Takvim hızlı işlemleri"
          className="fixed z-[100] w-56 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-xl"
          style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
          onClick={(event) => event.stopPropagation()}
        >
          {contextMenu.kind === 'cell' ? (
            <>
              <div className="border-b border-slate-100 px-3 py-2 text-xs text-slate-500">
                <span className="font-semibold text-slate-700">Oda {contextMenu.room.room_number}</span>
                <span className="block">{formatDateWithDay(contextMenu.date).dayNum} {formatDateWithDay(contextMenu.date).dayName}</span>
              </div>
              <button
                type="button"
                role="menuitem"
                disabled={contextMenu.covered || contextMenu.roomBlock || isPastDate(contextMenu.date)}
                onClick={() => {
                  onCellClick(contextMenu.room.id, contextMenu.date);
                  setContextMenu(null);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
              >
                <Plus className="h-4 w-4 text-amber-600" /> Rezervasyon oluştur
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onOpenRoomBlock?.(contextMenu.room);
                  setContextMenu(null);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
              >
                <Wrench className="h-4 w-4 text-rose-600" /> Odayı blokla / arıza bildir
              </button>
              {contextMenu.roomBlock && (
                <div className="mx-3 mb-2 rounded bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
                  Aktif blok: {contextMenu.roomBlock.reason || contextMenu.roomBlock.type}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="border-b border-slate-100 px-3 py-2 text-xs text-slate-500">
                <span className="block font-semibold text-slate-700">{formatGuestName(contextMenu.booking.guest_name) || 'Misafir'}</span>
                Oda {contextMenu.room.room_number}
              </div>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onBookingDoubleClick(contextMenu.booking);
                  setContextMenu(null);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
              >
                <ExternalLink className="h-4 w-4 text-blue-600" /> Rezervasyonu aç
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onOpenRoomBlock?.(contextMenu.room);
                  setContextMenu(null);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
              >
                <Wrench className="h-4 w-4 text-rose-600" /> Bu odayı blokla / arıza bildir
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default CalendarGrid;
