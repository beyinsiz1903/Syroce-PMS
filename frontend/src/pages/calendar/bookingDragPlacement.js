import { toDateStringUTC } from './calendarHelpers';

const DAY_MS = 86400000;
export const CALENDAR_DAY_WIDTH = 104;

const dayNumber = (date) => Date.parse(`${toDateStringUTC(date)}T00:00:00Z`) / DAY_MS;

// The cursor holds a point on the whole booking bar, not a particular cell.
export const bookingDragGrip = ({ bookingCheckIn, visibleStart, sourceLeft, clientX }) => ({
  gripPx: Math.max(0, clientX - sourceLeft),
  visibleOffsetDays: dayNumber(visibleStart) - dayNumber(bookingCheckIn),
});

export const bookingDropCheckIn = ({ targetStart, targetLeft, clientX, gripPx, visibleOffsetDays }) => {
  // Snap the bar's leading edge to the nearest day. targetStart and targetLeft
  // may refer to either a date cell or an occupied reservation bar.
  const targetOffsetDays = Math.round((clientX - targetLeft - gripPx) / CALENDAR_DAY_WIDTH);
  return new Date((dayNumber(targetStart) + targetOffsetDays - visibleOffsetDays) * DAY_MS);
};
