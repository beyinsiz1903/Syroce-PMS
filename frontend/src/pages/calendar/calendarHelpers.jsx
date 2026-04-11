/**
 * Calendar utility functions - extracted from ReservationCalendar.js
 * Pure functions with no React dependency
 */

// Convert any date value to YYYY-MM-DD string (timezone-safe)
export const toDateStringUTC = (value) => {
  if (typeof value === 'string') {
    return value.slice(0, 10);
  }
  const d = new Date(value);
  const year = d.getUTCFullYear();
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Check if booking overlaps with date
export const isBookingOnDate = (booking, date) => {
  const dayStr = toDateStringUTC(date);
  const checkIn = toDateStringUTC(booking.check_in);
  const checkOut = toDateStringUTC(booking.check_out);
  return dayStr >= checkIn && dayStr < checkOut;
};

// Check if booking starts on this date
export const isBookingStart = (booking, date) => {
  return toDateStringUTC(date) === toDateStringUTC(booking.check_in);
};

// Check if room is occupied on specific day
export const isRoomOccupiedOnDay = (roomId, day, bookings) => {
  const dayStr = toDateStringUTC(day);
  return bookings.some(b => {
    if (b.room_id !== roomId) return false;
    if (b.status === 'cancelled' || b.status === 'checked_out' || b.status === 'no_show') return false;
    const checkIn = toDateStringUTC(b.check_in);
    const checkOut = toDateStringUTC(b.check_out);
    return dayStr >= checkIn && dayStr < checkOut;
  });
};

// Get booking for room on specific date
export const getBookingForRoomOnDate = (roomId, date, bookings) => {
  const dayStr = toDateStringUTC(date);
  return bookings.find(booking => {
    if (booking.room_id !== roomId) return false;
    if (booking.status === 'cancelled' || booking.status === 'checked_out' || booking.status === 'no_show') return false;
    const checkIn = toDateStringUTC(booking.check_in);
    const checkOut = toDateStringUTC(booking.check_out);
    return dayStr >= checkIn && dayStr < checkOut;
  });
};

// Get room block for room on specific date
export const getRoomBlockForDate = (roomId, date, roomBlocks) => {
  const dayStr = toDateStringUTC(date);
  return roomBlocks.find(block => {
    if (block.room_id !== roomId || block.status !== 'active') return false;
    const blockStart = toDateStringUTC(block.start_date);
    const blockEnd = block.end_date ? toDateStringUTC(block.end_date) : '9999-12-31';
    return dayStr >= blockStart && dayStr <= blockEnd;
  });
};

// Check if block starts on this date
export const isBlockStart = (block, date) => {
  return toDateStringUTC(date) === toDateStringUTC(block.start_date);
};

// Calculate block span (visible days)
export const calculateBlockSpan = (block, startDate, daysToShow) => {
  const blockStart = toDateStringUTC(block.start_date);
  const blockEnd = block.end_date ? toDateStringUTC(block.end_date) : '9999-12-31';
  const rangeStart = toDateStringUTC(startDate);
  const rangeEndDate = new Date(startDate);
  rangeEndDate.setDate(rangeEndDate.getDate() + daysToShow);
  const rangeEnd = toDateStringUTC(rangeEndDate);
  const visibleStart = blockStart > rangeStart ? blockStart : rangeStart;
  const visibleEnd = blockEnd < rangeEnd ? blockEnd : rangeEnd;
  const startMs = new Date(visibleStart).getTime();
  const endMs = new Date(visibleEnd).getTime();
  const days = Math.ceil((endMs - startMs) / (1000 * 60 * 60 * 24));
  return Math.max(1, Math.min(days, daysToShow));
};

// Calculate booking span width (visible days)
export const calculateBookingSpan = (booking, startDate, daysToShow) => {
  const checkIn = toDateStringUTC(booking.check_in);
  const checkOut = toDateStringUTC(booking.check_out);
  const rangeStart = toDateStringUTC(startDate);
  const rangeEndDate = new Date(startDate);
  rangeEndDate.setDate(rangeEndDate.getDate() + daysToShow);
  const rangeEnd = toDateStringUTC(rangeEndDate);
  const effectiveStart = checkIn < rangeStart ? rangeStart : checkIn;
  const effectiveEnd = checkOut > rangeEnd ? rangeEnd : checkOut;
  const startMs = new Date(effectiveStart).getTime();
  const endMs = new Date(effectiveEnd).getTime();
  const nights = Math.ceil((endMs - startMs) / (1000 * 60 * 60 * 24));
  return Math.max(1, nights);
};

// Status color mapping
export const getStatusColor = (status) => {
  const colors = {
    confirmed: 'bg-blue-600',
    checked_in: 'bg-green-600',
    checked_out: 'bg-slate-400',
    cancelled: 'bg-red-500',
    guaranteed: 'bg-cyan-600'
  };
  return colors[status] || 'bg-blue-500';
};

// Market segment color
export const getSegmentColor = (segment) => {
  const colors = {
    corporate: 'bg-blue-600',
    'ota': 'bg-purple-600',
    'walk_in': 'bg-orange-500',
    'walk-in': 'bg-orange-500',
    group: 'bg-green-600',
    leisure: 'bg-pink-500',
    government: 'bg-indigo-600',
    default: 'bg-blue-500'
  };
  return colors[segment?.toLowerCase()] || colors.default;
};

// Rate type info
export const getRateTypeInfo = (booking) => {
  const rateTypes = {
    'corp_std': { label: 'CORP-STD', color: 'text-blue-300' },
    'corp_pref': { label: 'CORP-PREF', color: 'text-blue-200' },
    'gov': { label: 'GOV', color: 'text-indigo-300' },
    'leisure': { label: 'RACK', color: 'text-pink-300' },
    'ota': { label: 'OTA', color: 'text-purple-300' },
    'group': { label: 'GROUP', color: 'text-green-300' }
  };
  return rateTypes[booking.rate_type] || { label: booking.rate_type?.toUpperCase() || 'STD', color: 'text-gray-300' };
};

// Booking arrival/stayover/departure status
export const getBookingStatus = (booking, date) => {
  const dayStr = toDateStringUTC(date);
  const checkInStr = toDateStringUTC(booking.check_in);
  const checkOutStr = toDateStringUTC(booking.check_out);
  if (dayStr === checkInStr) return 'arrival';
  if (dayStr === checkOutStr) return 'departure';
  if (dayStr > checkInStr && dayStr < checkOutStr) return 'stayover';
  return null;
};

// Status label
export const getStatusLabel = (status) => {
  const labels = {
    confirmed: 'Confirmed',
    checked_in: 'In-House',
    checked_out: 'Departed',
    cancelled: 'Cancelled',
    guaranteed: 'Guaranteed'
  };
  return labels[status] || status;
};

// OTA info
export const getOTAInfo = (channel) => {
  const otaData = {
    'booking_com': { label: 'BKG', name: 'Booking.com', color: 'bg-indigo-600' },
    'expedia': { label: 'EXP', name: 'Expedia', color: 'bg-blue-600' },
    'airbnb': { label: 'ABNB', name: 'Airbnb', color: 'bg-red-600' },
    'agoda': { label: 'AGD', name: 'Agoda', color: 'bg-purple-600' },
    'hotels_com': { label: 'HTL', name: 'Hotels.com', color: 'bg-rose-600' },
    'direct': { label: 'DIR', name: 'Direct', color: 'bg-green-600' },
    'phone': { label: 'TEL', name: 'Phone', color: 'bg-gray-600' },
    'walk_in': { label: 'WLK', name: 'Walk-in', color: 'bg-orange-600' }
  };
  return otaData[channel] || { label: 'OTA', name: 'OTA', color: 'bg-gray-600' };
};

// Status-based booking color for calendar bars
// blue = confirmed, green = checked_in (in-house), red tint = checked_out, teal = guaranteed
export const getBookingStatusColor = (booking) => {
  const status = booking.status;
  const today = new Date().toISOString().slice(0, 10);
  const checkIn = toDateStringUTC(booking.check_in);
  const checkOut = toDateStringUTC(booking.check_out);
  // In-house: vibrant green
  if (status === 'checked_in') return { bg: '#16a34a', border: '#15803d' };
  // Departed: muted slate
  if (status === 'checked_out') return { bg: '#94a3b8', border: '#64748b' };
  // Past but not checked out: soft red
  if (checkOut <= today) return { bg: '#f87171', border: '#ef4444' };
  // Guaranteed: vivid teal
  if (status === 'guaranteed') return { bg: '#0891b2', border: '#0e7490' };
  // Arriving today: vivid orange
  if (checkIn === today && status === 'confirmed') return { bg: '#f97316', border: '#ea580c' };
  // Confirmed future: vibrant blue
  if (status === 'confirmed') return { bg: '#2563eb', border: '#1d4ed8' };
  // Default: blue
  return { bg: '#3b82f6', border: '#2563eb' };
};

// Source-based booking card color mapping (legacy, kept for compatibility)
export const getSourceColor = (booking) => {
  const channel = (booking.ota_channel || booking.source_channel || booking.channel || booking.source || '').toLowerCase();
  if (channel.includes('expedia')) return { bg: '#F97316', border: '#EA580C', label: 'Expedia' };
  if (channel.includes('booking')) return { bg: '#1D4ED8', border: '#1E40AF', label: 'Booking.com' };
  if (channel.includes('tatilbudur')) return { bg: '#2563EB', border: '#1D4ED8', label: 'Tatilbudur.com' };
  if (channel.includes('airbnb')) return { bg: '#E11D48', border: '#BE123C', label: 'Airbnb' };
  if (channel.includes('agoda')) return { bg: '#7C3AED', border: '#6D28D9', label: 'Agoda' };
  if (channel.includes('hotels')) return { bg: '#BE123C', border: '#9F1239', label: 'Hotels.com' };
  if (channel.includes('online')) return { bg: '#2563EB', border: '#1D4ED8', label: 'Online' };
  if (channel.includes('setur')) return { bg: '#0D9488', border: '#0F766E', label: 'Setur' };
  if (channel === 'direct' || channel === 'phone' || channel === 'walk_in' || channel === 'walk-in') return { bg: '#374151', border: '#1F2937', label: 'Kesin' };
  return { bg: '#374151', border: '#1F2937', label: 'Kesin' };
};

// Turkish day names
export const turkishDayNames = ['Paz', 'Pts', 'Sal', 'Car', 'Per', 'Cum', 'Cts'];

export const formatDateWithDay = (date) => {
  const dayName = turkishDayNames[date.getUTCDay()];
  const dayNum = String(date.getUTCDate()).padStart(2, '0');
  return { dayName, dayNum };
};

export const isWeekend = (date) => {
  const day = date.getUTCDay();
  return day === 0 || day === 6;
};

export const isToday = (date) => {
  const today = new Date();
  return date.toDateString() === today.toDateString();
};

// Check if date is before today (for visual styling of past dates)
export const isPastDate = (date) => {
  const dateStr = toDateStringUTC(date);
  const today = new Date().toISOString().slice(0, 10);
  return dateStr < today;
};

// Heatmap
export const getHeatmapColor = (intensity) => {
  const colors = {
    'critical': 'bg-red-100 border-red-300',
    'high': 'bg-orange-100 border-orange-300',
    'moderate': 'bg-yellow-100 border-yellow-300',
    'medium': 'bg-green-100 border-green-300',
    'low': 'bg-white'
  };
  return colors[intensity] || colors.low;
};

// Get unassigned bookings for a room type
export const getUnassignedBookingsForType = (roomType, bookings, dateRange) => {
  const rangeStart = dateRange.length > 0 ? toDateStringUTC(dateRange[0]) : '';
  const rangeEnd = dateRange.length > 0 ? toDateStringUTC(dateRange[dateRange.length - 1]) : '';
  const rtLower = roomType.toLowerCase();
  return bookings.filter(booking => {
    if (booking.status === 'cancelled' || booking.status === 'checked_out' || booking.status === 'no_show') return false;
    if (booking.room_id) return false;
    // Match by room_type OR room_type_id (OTA imports may use provider room names)
    const bType = (booking.room_type || '').toLowerCase();
    const bTypeId = (booking.room_type_id || '').toLowerCase();
    if (bType !== rtLower && bTypeId !== rtLower) return false;
    if (rangeStart && rangeEnd) {
      const checkIn = toDateStringUTC(booking.check_in);
      const checkOut = toDateStringUTC(booking.check_out);
      if (checkIn > rangeEnd || checkOut <= rangeStart) return false;
    }
    return true;
  });
};

// Compute lane allocation for unassigned bookings
export const computeUnassignedLanes = (unassignedBookings) => {
  if (!unassignedBookings.length) return { lanes: {}, maxLane: 0 };
  const sorted = [...unassignedBookings].sort((a, b) => {
    const aIn = toDateStringUTC(a.check_in);
    const bIn = toDateStringUTC(b.check_in);
    if (aIn !== bIn) return aIn < bIn ? -1 : 1;
    const aOut = toDateStringUTC(a.check_out);
    const bOut = toDateStringUTC(b.check_out);
    return aOut < bOut ? -1 : 1;
  });
  const lanes = {};
  const laneEnds = [];
  let maxLane = 0;
  for (const booking of sorted) {
    const checkIn = toDateStringUTC(booking.check_in);
    let placed = false;
    for (let i = 0; i < laneEnds.length; i++) {
      if (checkIn >= laneEnds[i]) {
        lanes[booking.id] = i;
        laneEnds[i] = toDateStringUTC(booking.check_out);
        placed = true;
        break;
      }
    }
    if (!placed) {
      const lane = laneEnds.length;
      lanes[booking.id] = lane;
      laneEnds.push(toDateStringUTC(booking.check_out));
      if (lane > maxLane) maxLane = lane;
    }
  }
  return { lanes, maxLane };
};

// Unassigned booking urgency classification
export const getUnassignedUrgency = (booking) => {
  const today = toDateStringUTC(new Date());
  const tomorrow = (() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return toDateStringUTC(d);
  })();
  const checkIn = toDateStringUTC(booking.check_in);

  if (checkIn < today) return { level: 'overdue', label: 'Gecikmiş', days: -1, color: 'red' };
  if (checkIn === today) return { level: 'today', label: 'Bugün!', days: 0, color: 'orange' };
  if (checkIn === tomorrow) return { level: 'tomorrow', label: 'Yarın', days: 1, color: 'amber' };
  const diffMs = new Date(checkIn) - new Date(today);
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  return { level: 'future', label: `${diffDays} gün`, days: diffDays, color: 'blue' };
};

export const getUrgencyBarColors = (urgency) => {
  const map = {
    overdue:  { bg: '#fecaca', border: '#ef4444', stripe: '#dc2626', text: '#991b1b', badge: 'bg-red-600' },
    today:    { bg: '#fed7aa', border: '#f97316', stripe: '#ea580c', text: '#9a3412', badge: 'bg-orange-500' },
    tomorrow: { bg: '#fde68a', border: '#f59e0b', stripe: '#d97706', text: '#92400e', badge: 'bg-amber-500' },
    future:   { bg: '#bfdbfe', border: '#3b82f6', stripe: '#2563eb', text: '#1e40af', badge: 'bg-blue-500' },
  };
  return map[urgency?.level] || map.future;
};

export const sortByUrgency = (bookings) => {
  const order = { overdue: 0, today: 1, tomorrow: 2, future: 3 };
  return [...bookings].sort((a, b) => {
    const ua = getUnassignedUrgency(a);
    const ub = getUnassignedUrgency(b);
    if (order[ua.level] !== order[ub.level]) return order[ua.level] - order[ub.level];
    return new Date(a.check_in) - new Date(b.check_in);
  });
};

// Generate date range
export const getDateRange = (currentDate, daysToShow) => {
  const dates = [];
  const start = new Date(currentDate);
  const startYear = start.getFullYear();
  const startMonth = start.getMonth();
  const startDay = start.getDate();
  for (let i = 0; i < daysToShow; i++) {
    const date = new Date(Date.UTC(startYear, startMonth, startDay + i));
    dates.push(date);
  }
  return dates;
};
