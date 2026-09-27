const firstValue = (...values) => values.find((value) => value !== undefined && value !== null && value !== '');

export const mergeQuickPanelDetail = (calendarBooking, detail) => {
  const fullBooking = detail?.booking || {};
  const primaryGuest = detail?.guest || detail?.guests?.[0] || {};
  return {
    ...calendarBooking,
    ...fullBooking,
    guest_name: firstValue(primaryGuest.name, primaryGuest.full_name, fullBooking.guest_name, calendarBooking?.guest_name),
    guest_email: firstValue(primaryGuest.email, primaryGuest.email_address, fullBooking.guest_email, calendarBooking?.guest_email),
    guest_phone: firstValue(primaryGuest.phone, primaryGuest.phone_number, fullBooking.guest_phone, calendarBooking?.guest_phone),
    special_requests: firstValue(fullBooking.special_requests, detail?.special_requests, calendarBooking?.special_requests),
    remaining_balance: firstValue(
      detail?.summary?.reservation_total_due,
      detail?.summary?.balance,
      fullBooking.remaining_balance,
      calendarBooking?.remaining_balance,
    ),
  };
};

export const primaryQuickPanelFolio = (detail) => detail?.folios?.[0] || detail?.folio || null;
