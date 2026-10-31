import { HOTEL_EVENT_TIME_ZONE_LABEL, formatHotelEventTimestamp, formatHotelEventTime, hotelEventDay } from './hotelEventTime';

// Keep the cashier's existing public precision and calendar-day contract.
export const CASHIER_TIME_ZONE_LABEL = HOTEL_EVENT_TIME_ZONE_LABEL;

export function formatCashierTimestamp(value, { seconds = false } = {}) {
  return formatHotelEventTimestamp(value, { seconds });
}

export function formatCashierTime(value) {
  return formatHotelEventTime(value, { seconds: false });
}

export function cashierCalendarDay(value = new Date()) {
  return hotelEventDay(value);
}
