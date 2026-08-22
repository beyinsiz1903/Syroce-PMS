export const normalizeRoomType = (value) => String(value || '')
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/ı/g, 'i')
  .toLocaleLowerCase('tr-TR')
  .replace(/[^a-z0-9]+/g, ' ')
  .trim();

export const formatGuestName = (value) => {
  const name = String(value || '').trim().replace(/\s+/g, ' ');
  if (!name) return '';
  const lower = name.toLocaleLowerCase('tr-TR');
  const upper = name.toLocaleUpperCase('tr-TR');
  if (name !== lower && name !== upper) return name;
  return lower
    .split(' ')
    .map(word => word.charAt(0).toLocaleUpperCase('tr-TR') + word.slice(1))
    .join(' ');
};

export const roomMatchesBookingType = (room, booking) => {
  const bookingTypes = [booking?.room_type_id, booking?.room_type]
    .map(normalizeRoomType)
    .filter(Boolean);
  const roomTypes = [room?.room_type_id, room?.room_type]
    .map(normalizeRoomType)
    .filter(Boolean);
  return bookingTypes.some(type => roomTypes.includes(type));
};

export const roomIsFreeForBooking = (room, booking, bookings) => {
  const checkIn = new Date(booking?.check_in);
  const checkOut = new Date(booking?.check_out);
  return !bookings.some(other => (
    other.room_id === room.id
    && other.id !== booking.id
    && !['cancelled', 'checked_out', 'no_show'].includes(other.status)
    && new Date(other.check_in) < checkOut
    && new Date(other.check_out) > checkIn
  ));
};
