import React from "react";
import { Calendar as CalendarIcon, Plus } from "lucide-react";
import {
  toDateStringUTC, isBookingOnDate, isBookingStart, isWeekend, isToday, isPastDate,
  formatDateWithDay, getBookingForRoomOnDate, getRoomBlockForDate,
  isBlockStart, calculateBlockSpan, calculateBookingSpan,
  getBookingStatusColor, getBookingStatus,
  getUnassignedBookingsForType, computeUnassignedLanes,
} from "./calendarHelpers";

// Compact grid constants
const CELL_W = 72;  // px per day column (was 96)
const CELL_CLS = 'w-[72px]'; // Tailwind class matching CELL_W
const CELL_H = 38;  // px room row height (was 52)
const BOOKING_H = 30; // px booking bar height (was 46)
const LANE_H = 32;  // px per unassigned lane (was 44)

const CalendarGrid = ({
  rooms,
  bookings,
  roomBlocks,
  dateRange,
  daysToShow,
  currentDate,
  conflicts,
  draggingBooking,
  dragOverCell,
  showAIPanel,
  showDeluxePanel,
  groupColorMap,
  setGroupColorMap,
  // Enterprise / AI helpers
  rateLeakages,
  aiRoomMoves,
  aiOverbookingSolutions,
  aiNoShowPredictions,
  groupBookings: deluxeGroupBookings,
  // Handlers
  onCellClick,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
  onBookingDoubleClick,
}) => {

  const hasConflict = (roomId, date) => {
    return conflicts.some(c =>
      c.room_id === roomId &&
      date >= new Date(c.overlap_start) &&
      date < new Date(c.overlap_end)
    );
  };

  const hasRateLeakage = (bookingId) => {
    return rateLeakages.find(l => l.booking_id === bookingId);
  };

  const getAIRecommendation = (bookingId) => {
    const roomMove = aiRoomMoves.find(r => r.booking_id === bookingId);
    const overbooking = aiOverbookingSolutions.find(s => s.booking_id === bookingId);
    return roomMove || overbooking;
  };

  const getNoShowRisk = (bookingId) => {
    return aiNoShowPredictions.find(p => p.booking_id === bookingId);
  };

  const isGroupBooking = (bookingId) => {
    return (deluxeGroupBookings || []).some(g => g.booking_ids?.includes(bookingId));
  };

  const getGroupInfo = (bookingId) => {
    return (deluxeGroupBookings || []).find(g => g.booking_ids?.includes(bookingId));
  };

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
    <div className="bg-white rounded-lg border border-gray-200 relative" data-testid="calendar-grid">
      {/* Date Header Row - STICKY */}
      <div className="sticky top-16 z-40 bg-white border-b border-gray-300 overflow-x-auto">
        <div className="min-w-max">
          <div className="flex">
            <div className="w-28 flex-shrink-0 border-r border-gray-200"></div>
            <div className="flex-1 text-center text-[10px] font-semibold text-gray-500 py-0.5">
              {dateRange.length > 0 && dateRange[Math.floor(dateRange.length / 2)].toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' })}
            </div>
          </div>
          <div className="flex bg-white">
            <div className="w-28 flex-shrink-0 px-2 py-1 border-r border-gray-200 text-[10px] text-gray-500 font-medium flex items-end">
              <span className="cursor-pointer hover:text-gray-700">Daralt ^</span>
            </div>
            {dateRange.map((date, idx) => {
              const { dayName, dayNum } = formatDateWithDay(date);
              const weekend = isWeekend(date);
              const today = isToday(date);
              const past = isPastDate(date);
              return (
                <div
                  key={idx}
                  className={`${CELL_CLS} flex-shrink-0 py-1 border-r text-center ${
                    today ? 'bg-blue-50 border-blue-200' : past ? 'bg-gray-100/60 border-gray-200' : weekend ? 'bg-orange-50 border-gray-200' : 'bg-white border-gray-200'
                  }`}
                  data-testid={`date-header-${dayNum}`}
                >
                  <div className={`text-[9px] font-semibold tracking-wide ${today ? 'text-blue-600' : past ? 'text-gray-400' : 'text-gray-500'}`}>
                    {dayName}
                  </div>
                  <div className={`text-sm font-bold ${today ? 'text-blue-600' : past ? 'text-gray-400' : 'text-gray-800'}`}>
                    {dayNum}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Room Rows */}
      <div className="overflow-x-auto">
        <div className="min-w-max">
          {rooms.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              <CalendarIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Oda bulunamadi</p>
            </div>
          ) : (
            sortedTypes.map((roomType) => {
              const typeRooms = groupedRooms[roomType];
              const unassignedForType = getUnassignedBookingsForType(roomType, bookings, dateRange);

              return (
                <div key={roomType}>
                  {/* Room Type Header */}
                  <div className="bg-blue-50/70 border-b border-blue-200">
                    <div className="flex">
                      <div className="w-28 flex-shrink-0 px-2 py-1.5 border-r border-blue-200 flex items-center">
                        <span className="font-bold text-xs text-gray-800" data-testid={`room-type-${roomType}`}>
                          {roomType} ^
                        </span>
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
                        const unassignedOnDate = bookings.filter(b => {
                          if (b.status === 'cancelled' || b.status === 'checked_out' || b.status === 'no_show') return false;
                          if (b.room_id) return false;
                          const bType = (b.room_type || '').toLowerCase();
                          if (bType !== roomType.toLowerCase()) return false;
                          return isBookingOnDate(b, date);
                        });
                        const occupiedCount = assignedBookings.length + unassignedOnDate.length;
                        const totalTypeRooms = typeRooms.length;
                        const isFull = occupiedCount >= totalTypeRooms;
                        const allBookingsForPrice = [...assignedBookings, ...unassignedOnDate];
                        const avgPrice = allBookingsForPrice.length > 0
                          ? Math.round(allBookingsForPrice.reduce((sum, b) => {
                              const nights = Math.max(1, Math.ceil((new Date(b.check_out) - new Date(b.check_in)) / (1000 * 60 * 60 * 24)));
                              return sum + (b.total_amount || 0) / nights;
                            }, 0) / allBookingsForPrice.length)
                          : typeRooms[0]?.base_price || 0;

                        return (
                          <div
                            key={idx}
                            className={`${CELL_CLS} flex-shrink-0 px-0.5 py-1 border-r text-center text-[9px] ${
                              past ? 'bg-gray-100/70 border-gray-200' : weekend ? 'bg-blue-100/50 border-blue-200' : 'bg-blue-50/80 border-blue-200'
                            }`}
                          >
                            <div className={`font-medium truncate ${past ? 'text-gray-400' : 'text-gray-700'}`}>
                              {avgPrice > 0 ? `${avgPrice.toLocaleString('tr-TR')} TL` : '-'}
                            </div>
                            <div className="flex items-center justify-center gap-0.5 mt-0.5">
                              <div className={`w-1.5 h-1.5 rounded-full ${isFull ? 'bg-red-500' : occupiedCount > 0 ? 'bg-orange-500' : 'bg-green-500'}`}></div>
                              <span className={`text-[8px] font-bold ${isFull ? 'text-red-600' : occupiedCount > 0 ? 'text-orange-600' : 'text-green-700'}`}>
                                {occupiedCount}/{totalTypeRooms}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Unassigned Bookings Row */}
                  {unassignedForType.length > 0 && (() => {
                    const { lanes, maxLane } = computeUnassignedLanes(unassignedForType);
                    const rowHeight = (maxLane + 1) * LANE_H + 6;
                    return (
                      <div className="flex border-b border-dashed border-blue-200 bg-blue-50/20">
                        <div className="w-28 flex-shrink-0 px-2 py-1 border-r border-gray-200 bg-blue-50/40" style={{ height: `${rowHeight}px` }}>
                          <div className="flex items-center gap-1">
                            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse"></div>
                            <div className="font-bold text-[9px] text-blue-700">Atanmamis</div>
                          </div>
                          {unassignedForType.length > 1 && (
                            <div className="text-[8px] text-blue-500 ml-3">{unassignedForType.length} rez.</div>
                          )}
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
                            const statusColor = getBookingStatusColor(booking);
                            return (
                              <div
                                key={booking.id}
                                draggable
                                onDragStart={(e) => onDragStart(e, booking)}
                                onDragEnd={onDragEnd}
                                onDoubleClick={() => onBookingDoubleClick(booking)}
                                className="absolute rounded text-white text-[10px] shadow-sm hover:shadow-md transition-all cursor-move z-20 border"
                                style={{
                                  left: `${startIdx * CELL_W + 2}px`,
                                  top: `${lane * LANE_H + 3}px`,
                                  width: `${span * CELL_W - 4}px`,
                                  height: `${LANE_H - 6}px`,
                                  backgroundColor: statusColor.bg,
                                  borderColor: statusColor.border,
                                }}
                                data-testid={`unassigned-booking-${booking.id}`}
                                title={`${booking.guest_name} - Odaya surukleyin`}
                              >
                                <div className="px-1.5 py-0.5 h-full relative overflow-hidden">
                                  <div className="font-extrabold text-[10px] truncate text-white leading-tight">
                                    {booking.guest_name || 'Misafir'}
                                  </div>
                                  <div className="text-[8px] text-white/80 truncate">
                                    Oda ata
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
                  {typeRooms.map((room) => {
                    const hasBookingToday = bookings.some(b => b.room_id === room.id && isBookingOnDate(b, new Date()) && b.status !== 'cancelled' && b.status !== 'checked_out' && b.status !== 'no_show');
                    return (
                      <div key={room.id} className="flex border-b border-gray-100 hover:bg-gray-50/50 transition-colors">
                        <div className="w-28 flex-shrink-0 px-2 py-1 border-r border-gray-200 bg-white flex items-center">
                          <div className="flex items-center gap-1">
                            <div className={`w-1.5 h-1.5 rounded-full ${hasBookingToday ? 'bg-red-500' : 'bg-green-500'}`}></div>
                            <div className="font-bold text-xs text-gray-800" data-testid={`room-${room.room_number}`}>{room.room_number}</div>
                          </div>
                        </div>
                        <div className="flex relative" style={{ width: `${daysToShow * CELL_W}px` }}>
                          {dateRange.map((date, idx) => {
                            const booking = getBookingForRoomOnDate(room.id, date, bookings);
                            const bIsStart = booking && isBookingStart(booking, date);
                            const roomBlock = getRoomBlockForDate(room.id, date, roomBlocks);
                            const bBlockIsStart = roomBlock && isBlockStart(roomBlock, date);
                            const isDragOver = dragOverCell?.roomId === room.id &&
                              new Date(dragOverCell.date).toDateString() === date.toDateString();
                            const past = isPastDate(date);

                            return (
                              <div
                                key={idx}
                                className={`${CELL_CLS} flex-shrink-0 border-r border-gray-100 relative cursor-pointer transition-all ${
                                  past ? 'bg-gray-100/50' : isToday(date) ? 'bg-blue-50/60' : isWeekend(date) ? 'bg-orange-50/30' : 'bg-white hover:bg-gray-50'
                                } ${isDragOver ? 'bg-emerald-50 ring-1 ring-emerald-400' : ''}
                                ${roomBlock ? 'bg-gray-100/60 border-dashed' : ''}`}
                                style={{
                                  height: `${CELL_H}px`, minHeight: `${CELL_H}px`, overflow: 'visible',
                                  ...(past && !roomBlock ? { backgroundImage: 'repeating-linear-gradient(135deg, transparent, transparent 8px, rgba(0,0,0,0.02) 8px, rgba(0,0,0,0.02) 9px)' } : {})
                                }}
                                onClick={() => !booking && !roomBlock && onCellClick(room.id, date)}
                                onDragOver={(e) => onDragOver(e, room.id, date)}
                                onDragLeave={onDragLeave}
                                onDrop={(e) => onDrop(e, room.id, date)}
                                title={roomBlock ? `${roomBlock.type.toUpperCase()}: ${roomBlock.reason}` : ''}
                              >
                                {/* Room Block Indicator */}
                                {bBlockIsStart && roomBlock && (
                                  <div
                                    className={`absolute top-0 left-0 h-full opacity-60 border-2 ${
                                      roomBlock.type === 'out_of_order' ? 'bg-red-600 border-red-700' :
                                      roomBlock.type === 'out_of_service' ? 'bg-orange-500 border-orange-600' :
                                      'bg-yellow-600 border-yellow-700'
                                    }`}
                                    style={{
                                      width: `${calculateBlockSpan(roomBlock, currentDate, daysToShow) * CELL_W - 4}px`,
                                      backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(255,255,255,.1) 10px, rgba(255,255,255,.1) 20px)',
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

                                {/* Empty cell indicator */}
                                {!booking && !roomBlock && (
                                  <div className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                                    <Plus className="w-4 h-4 text-gray-400" />
                                  </div>
                                )}

                                {/* Booking bar */}
                                {bIsStart && booking && (() => {
                                  const statusColor = getBookingStatusColor(booking);
                                  return (
                                  <div
                                    draggable
                                    onDragStart={(e) => onDragStart(e, booking)}
                                    onDragEnd={onDragEnd}
                                    onDoubleClick={() => onBookingDoubleClick(booking)}
                                    className={`absolute top-1 left-0.5 rounded text-white text-[10px] shadow-sm hover:shadow-md transition-all cursor-move z-20 group ${
                                      draggingBooking?.id === booking.id ? 'opacity-50 scale-95' : ''
                                    } ${hasConflict(room.id, date) ? 'ring-2 ring-red-500 animate-pulse' : ''}
                                    ${showDeluxePanel && isGroupBooking(booking.id) ? 'ring-2 ring-amber-400' : ''}`}
                                    style={{
                                      width: `${calculateBookingSpan(booking, currentDate, daysToShow) * CELL_W - 4}px`,
                                      height: `${BOOKING_H}px`,
                                      backgroundColor: statusColor.bg,
                                      borderLeft: `3px solid ${statusColor.border}`,
                                    }}
                                    data-testid={`booking-bar-${booking.id}`}
                                    title={`${booking.guest_name}`}
                                  >
                                    <div className="px-1.5 py-0.5 relative overflow-hidden" style={{ height: `${BOOKING_H}px` }}>
                                      <div className="font-extrabold text-[10px] truncate pr-3 text-white leading-tight">
                                        {booking.guest_name || 'Misafir'}
                                      </div>
                                      <div className="text-[8px] text-white/80 truncate flex items-center gap-0.5">
                                        {booking.adults && <span>Ks: {(booking.adults || 0) + (booking.children || 0)}</span>}
                                      </div>
                                      <div className="absolute top-0.5 right-0.5 flex flex-col space-y-0.5 items-end">
                                        {showAIPanel && getAIRecommendation(booking.id) && (
                                          <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white text-[7px] font-bold px-0.5 py-0 rounded animate-pulse" title="AI Recommendation">
                                            AI
                                          </div>
                                        )}
                                        {showAIPanel && getNoShowRisk(booking.id) && getNoShowRisk(booking.id).risk_level === 'high' && (
                                          <div className="bg-red-600 text-white text-[7px] font-bold px-0.5 py-0 rounded" title={`High No-Show Risk: ${getNoShowRisk(booking.id).risk_score}%`}>
                                            !
                                          </div>
                                        )}
                                        {showDeluxePanel && isGroupBooking(booking.id) && (
                                          <div className="bg-gradient-to-r from-amber-500 to-orange-600 text-white text-[7px] font-bold px-0.5 py-0 rounded" title={`Group: ${getGroupInfo(booking.id)?.company_name}`}>
                                            G
                                          </div>
                                        )}
                                        <div className="flex space-x-0.5">
                                          {getBookingStatus(booking, date) === 'arrival' && (
                                            <div className="bg-white text-green-600 rounded-full w-3.5 h-3.5 flex items-center justify-center text-[8px] font-bold" title="Arrival">A</div>
                                          )}
                                          {getBookingStatus(booking, date) === 'departure' && (
                                            <div className="bg-white text-red-600 rounded-full w-3.5 h-3.5 flex items-center justify-center text-[8px] font-bold" title="Departure">D</div>
                                          )}
                                          {getBookingStatus(booking, date) === 'stayover' && (
                                            <div className="bg-white text-blue-600 rounded-full w-3.5 h-3.5 flex items-center justify-center text-[8px] font-bold" title="Stayover">S</div>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                    {hasRateLeakage(booking.id) && (
                                      <div className="absolute top-0 left-0 bg-red-600 text-white text-[7px] px-0.5 rounded-br font-bold" title={`Rate Leakage: -$${hasRateLeakage(booking.id).difference_per_night}/night`}>
                                        LEAK
                                      </div>
                                    )}
                                    {hasConflict(room.id, date) && (
                                      <div className="absolute top-0 right-0 bg-red-600 text-white text-[7px] px-0.5 rounded-bl font-bold animate-pulse">
                                        !!
                                      </div>
                                    )}
                                  </div>
                                  );
                                })()}
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
