const text = value => typeof value === 'string' ? value.trim() : '';

// Provider instructions and channel references are not PMS receipt evidence.
export const exelyReservationDetails = (booking = {}) => {
  const sources = [booking.booking_source, booking.channel, booking.ota_channel, booking.source_channel,
    booking.source?.provider];
  if (!sources.some(value => text(value).toLowerCase() === 'exely')) return null;
  const references = Array.isArray(booking.channel_reservation_ids)
    ? booking.channel_reservation_ids.map(text).filter(Boolean) : [];
  if (text(booking.channel_reservation_id)) references.push(text(booking.channel_reservation_id));
  return {
    channel: text(booking.provider_channel_name),
    reservationId: text(booking.provider_group_reservation_id) || text(booking.ota_confirmation),
    channelReservationIds: [...new Set(references)],
    paymentMethod: text(booking.provider_payment_method) || text(booking.payment_method),
  };
};
