import React from "react";
import { Calendar as CalendarIcon, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  toDateStringUTC, isBookingOnDate, isBookingStart, isWeekend, isToday,
  formatDateWithDay, getBookingForRoomOnDate, getRoomBlockForDate,
  isBlockStart, calculateBlockSpan, calculateBookingSpan,
  getSourceColor, getBookingStatus, getOTAInfo,
  getUnassignedBookingsForType, computeUnassignedLanes,
} from "./calendarHelpers";

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
            <div className="w-32 flex-shrink-0 border-r border-gray-200"></div>
            <div className="flex-1 text-center text-xs font-semibold text-gray-500 py-1">
              {dateRange.length > 0 && dateRange[Math.floor(dateRange.length / 2)].toLocaleDateString('tr-TR', { month: 'long', year: 'numeric' })}
            </div>
          </div>
          <div className="flex bg-white">
            <div className="w-32 flex-shrink-0 px-3 py-2 border-r border-gray-200 text-xs text-gray-500 font-medium flex items-end">
              <span className="cursor-pointer hover:text-gray-700">Listeyi daralt ^</span>
            </div>
            {dateRange.map((date, idx) => {
              const { dayName, dayNum } = formatDateWithDay(date);
              const weekend = isWeekend(date);
              const today = isToday(date);
              return (
                <div
                  key={idx}
                  className={`w-24 flex-shrink-0 py-1.5 border-r text-center ${
                    today ? 'bg-blue-50 border-blue-200' : weekend ? 'bg-orange-50 border-gray-200' : 'bg-white border-gray-200'
                  }`}
                  data-testid={`date-header-${dayNum}`}
                >
                  <div className={`text-[10px] font-semibold tracking-wide ${today ? 'text-blue-600' : 'text-gray-500'}`}>
                    {dayName}
                  </div>
                  <div className={`text-base font-bold ${today ? 'text-blue-600' : 'text-gray-800'}`}>
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
                  <div className="bg-amber-50 border-b border-amber-200">
                    <div className="flex">
                      <div className="w-32 flex-shrink-0 px-3 py-2 border-r border-amber-200 flex items-center">
                        <span className="font-bold text-sm text-gray-800" data-testid={`room-type-${roomType}`}>
                          {roomType} ^
                        </span>
                      </div>
                      {dateRange.map((date, idx) => {
                        const weekend = isWeekend(date);
                        const typeBookings = bookings.filter(b => {
                          if (b.status === 'cancelled' || b.status === 'checked_out' || b.status === 'no_show') return false;
                          const room = rooms.find(r => r.id === b.room_id);
                          if (!room || (room.room_type || 'standard') !== roomType) return false;
                          return isBookingOnDate(b, date);
                        });
                        const occupiedCount = typeBookings.length;
                        const totalTypeRooms = typeRooms.length;
                        const isFull = occupiedCount >= totalTypeRooms;
                        const avgPrice = typeBookings.length > 0
                          ? Math.round(typeBookings.reduce((sum, b) => {
                              const nights = Math.max(1, Math.ceil((new Date(b.check_out) - new Date(b.check_in)) / (1000 * 60 * 60 * 24)));
                              return sum + (b.total_amount || 0) / nights;
                            }, 0) / typeBookings.length)
                          : typeRooms[0]?.base_price || 0;

                        return (
                          <div
                            key={idx}
                            className={`w-24 flex-shrink-0 px-1 py-1.5 border-r text-center text-[10px] ${
                              weekend ? 'bg-amber-100/60 border-amber-200' : 'bg-amber-50 border-amber-200'
                            }`}
                          >
                            <div className="text-gray-700 font-medium truncate">
                              {avgPrice > 0 ? `${avgPrice.toLocaleString('tr-TR')} TL` : '-'}
                            </div>
                            <div className="flex items-center justify-center gap-0.5 mt-0.5">
                              <div className={`w-1.5 h-1.5 rounded-full ${isFull ? 'bg-red-500' : 'bg-green-500'}`}></div>
                              <span className={`text-[9px] font-semibold ${isFull ? 'text-red-600' : 'text-green-700'}`}>
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
                    const laneHeight = 44;
                    const rowHeight = (maxLane + 1) * laneHeight + 8;
                    return (
                      <div className="flex border-b border-dashed border-amber-300 bg-amber-50/30">
                        <div className="w-32 flex-shrink-0 px-3 py-2 border-r border-gray-200 bg-amber-50/60" style={{ height: `${rowHeight}px` }}>
                          <div className="flex items-center gap-1.5">
                            <div className="w-1.5 h-1.5 bg-amber-500 rounded-full animate-pulse"></div>
                            <div className="font-semibold text-[10px] text-amber-700">Atanmamis Rez.</div>
                          </div>
                          {unassignedForType.length > 1 && (
                            <div className="text-[9px] text-amber-500 ml-3 mt-0.5">{unassignedForType.length} rez.</div>
                          )}
                        </div>
                        <div className="flex relative" style={{ width: `${daysToShow * 96}px`, height: `${rowHeight}px` }}>
                          {dateRange.map((date, idx) => {
                            const weekend = isWeekend(date);
                            return (
                              <div
                                key={idx}
                                className={`w-24 flex-shrink-0 border-r border-b relative ${
                                  weekend ? 'bg-amber-50/40 border-amber-100' : 'bg-amber-50/10 border-amber-100'
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
                            return (
                              <div
                                key={booking.id}
                                draggable
                                onDragStart={(e) => onDragStart(e, booking)}
                                onDragEnd={onDragEnd}
                                onDoubleClick={() => onBookingDoubleClick(booking)}
                                className="absolute rounded text-white text-xs shadow-sm hover:shadow-md transition-all cursor-move z-20 border border-amber-400"
                                style={{
                                  left: `${startIdx * 96 + 2}px`,
                                  top: `${lane * laneHeight + 4}px`,
                                  width: `${span * 96 - 4}px`,
                                  height: `${laneHeight - 6}px`,
                                  backgroundColor: getSourceColor(booking).bg,
                                  borderColor: getSourceColor(booking).border,
                                }}
                                data-testid={`unassigned-booking-${booking.id}`}
                                title={`${booking.guest_name} - Odaya surukleyin`}
                              >
                                <div className="px-2 py-1 h-full relative overflow-hidden">
                                  <div className="font-bold text-[11px] truncate text-white">
                                    {booking.guest_name || 'Misafir'}
                                  </div>
                                  <div className="text-[9px] text-white/80 truncate mt-0.5">
                                    {getSourceColor(booking).label} - Oda ata
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
                        <div className="w-32 flex-shrink-0 px-3 py-2 border-r border-gray-200 bg-white">
                          <div className="flex items-center gap-1.5">
                            <div className={`w-2 h-2 rounded-full ${hasBookingToday ? 'bg-red-500' : 'bg-green-500'}`}></div>
                            <div className="font-semibold text-sm text-gray-800" data-testid={`room-${room.room_number}`}>{room.room_number}</div>
                          </div>
                        </div>
                        <div className="flex relative" style={{ width: `${daysToShow * 96}px` }}>
                          {dateRange.map((date, idx) => {
                            const booking = getBookingForRoomOnDate(room.id, date, bookings);
                            const bIsStart = booking && isBookingStart(booking, date);
                            const roomBlock = getRoomBlockForDate(room.id, date, roomBlocks);
                            const bBlockIsStart = roomBlock && isBlockStart(roomBlock, date);
                            const isDragOver = dragOverCell?.roomId === room.id &&
                              new Date(dragOverCell.date).toDateString() === date.toDateString();

                            return (
                              <div
                                key={idx}
                                className={`w-24 flex-shrink-0 border-r border-gray-100 relative cursor-pointer transition-all ${
                                  isToday(date) ? 'bg-blue-50/60' : isWeekend(date) ? 'bg-orange-50/50' : 'bg-white hover:bg-gray-50'
                                } ${isDragOver ? 'bg-emerald-50 ring-1 ring-emerald-400' : ''}
                                ${roomBlock ? 'bg-gray-100/60 border-dashed' : ''}`}
                                style={{ height: '52px', minHeight: '52px', overflow: 'visible' }}
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
                                      width: `${calculateBlockSpan(roomBlock, currentDate, daysToShow) * 96 - 4}px`,
                                      backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(255,255,255,.1) 10px, rgba(255,255,255,.1) 20px)',
                                      zIndex: 5
                                    }}
                                    title={`${roomBlock.type.replace('_', ' ').toUpperCase()}: ${roomBlock.reason}\n${roomBlock.start_date} - ${roomBlock.end_date || 'Open-ended'}`}
                                  >
                                    <div className="p-1 text-white text-[10px] font-bold">
                                      {roomBlock.type === 'out_of_order' ? 'OOO' :
                                       roomBlock.type === 'out_of_service' ? 'OOS' : 'MNT'}
                                    </div>
                                  </div>
                                )}

                                {/* Empty cell indicator */}
                                {!booking && !roomBlock && (
                                  <div className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                                    <Plus className="w-6 h-6 text-gray-400" />
                                  </div>
                                )}

                                {/* Booking bar */}
                                {bIsStart && booking && (
                                  <div
                                    draggable
                                    onDragStart={(e) => onDragStart(e, booking)}
                                    onDragEnd={onDragEnd}
                                    onDoubleClick={() => onBookingDoubleClick(booking)}
                                    className={`absolute top-1 left-0.5 rounded text-white text-xs shadow-sm hover:shadow-md transition-all cursor-move z-20 group ${
                                      draggingBooking?.id === booking.id ? 'opacity-50 scale-95' : ''
                                    } ${hasConflict(room.id, date) ? 'ring-2 ring-red-500 animate-pulse' : ''}
                                    ${showDeluxePanel && isGroupBooking(booking.id) ? 'ring-2 ring-amber-400' : ''}`}
                                    style={{
                                      width: `${calculateBookingSpan(booking, currentDate, daysToShow) * 96 - 4}px`,
                                      height: '46px',
                                      backgroundColor: booking.group_booking_id ? getGroupColor(booking) : getSourceColor(booking).bg,
                                      borderLeft: `3px solid ${booking.group_booking_id ? getGroupColor(booking) : getSourceColor(booking).border}`,
                                      ...(booking.group_booking_id ? {
                                        backgroundImage: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.08) 8px, transparent 8px, transparent 16px)'
                                      } : {})
                                    }}
                                    data-testid={`booking-bar-${booking.id}`}
                                    title={`${booking.guest_name}`}
                                  >
                                    <div className="px-2 py-1 h-[46px] relative overflow-hidden">
                                      <div className="font-bold text-[11px] truncate pr-4 text-white">
                                        {booking.guest_name || 'Misafir'}
                                      </div>
                                      <div className="text-[9px] text-white/80 truncate mt-0.5 flex items-center gap-1">
                                        <span>{getSourceColor(booking).label}</span>
                                        {booking.adults && <span>Ks: {(booking.adults || 0) + (booking.children || 0)}</span>}
                                      </div>
                                      <div className="absolute top-1 right-1 flex flex-col space-y-1 items-end">
                                        {showAIPanel && getAIRecommendation(booking.id) && (
                                          <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white text-[8px] font-bold px-1 py-0.5 rounded animate-pulse" title="AI Recommendation">
                                            AI
                                          </div>
                                        )}
                                        {showAIPanel && getNoShowRisk(booking.id) && getNoShowRisk(booking.id).risk_level === 'high' && (
                                          <div className="bg-red-600 text-white text-[8px] font-bold px-1 py-0.5 rounded" title={`High No-Show Risk: ${getNoShowRisk(booking.id).risk_score}%`}>
                                            RISK
                                          </div>
                                        )}
                                        {showDeluxePanel && isGroupBooking(booking.id) && (
                                          <div className="bg-gradient-to-r from-amber-500 to-orange-600 text-white text-[8px] font-bold px-1 py-0.5 rounded" title={`Group: ${getGroupInfo(booking.id)?.company_name}`}>
                                            GRP
                                          </div>
                                        )}
                                        {booking.ota_channel && (
                                          <div className={`${getOTAInfo(booking.ota_channel).color} text-white text-[9px] font-bold px-1.5 py-0.5 rounded`} title={getOTAInfo(booking.ota_channel).name}>
                                            {getOTAInfo(booking.ota_channel).label}
                                          </div>
                                        )}
                                        <div className="flex space-x-1">
                                          {getBookingStatus(booking, date) === 'arrival' && (
                                            <div className="bg-white text-green-600 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold" title="Arrival">A</div>
                                          )}
                                          {getBookingStatus(booking, date) === 'departure' && (
                                            <div className="bg-white text-red-600 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold" title="Departure">D</div>
                                          )}
                                          {getBookingStatus(booking, date) === 'stayover' && (
                                            <div className="bg-white text-blue-600 rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold" title="Stayover">S</div>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                    {hasRateLeakage(booking.id) && (
                                      <div className="absolute top-0 left-0 bg-red-600 text-white text-[8px] px-1 py-0.5 rounded-br font-bold" title={`Rate Leakage: -$${hasRateLeakage(booking.id).difference_per_night}/night`}>
                                        LEAK
                                      </div>
                                    )}
                                    {hasConflict(room.id, date) && (
                                      <div className="absolute top-0 right-0 bg-red-600 text-white text-[8px] px-1 py-0.5 rounded-bl font-bold animate-pulse">
                                        CONFLICT
                                      </div>
                                    )}
                                  </div>
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
