export function resetUnassignedListScroll(listElement) {
  if (!listElement) return false;

  listElement.scrollTop = 0;
  return true;
}

export function isMappingIssue(booking) {
  return booking.queue_kind === 'mapping_required' || booking.status === 'pending_mapping'
    || booking.booking_source === 'ota_unmatched_hold' || booking.source?.kind === 'ota_unmatched_hold'
    || booking.allocation_source === 'ota_unmatched_hold' || booking.is_inventory_hold === true;
}

export function mergeUnassignedAttention(bookings, mappingIssues = []) {
  const groups = new Map();
  for (const booking of [...mappingIssues, ...bookings]) {
    if ((booking.room_id && !isMappingIssue(booking)) || ['cancelled', 'checked_out', 'no_show', 'resolved'].includes(booking.status)) continue;
    if (!isMappingIssue(booking)) {
      groups.set(`booking:${booking.id}`, booking);
      continue;
    }
    const provider = booking.provider || booking.source?.provider || 'unknown';
    const external = booking.external_reservation_id || booking.source?.external_reservation_id;
    const key = `mapping:${booking.property_id || booking.tenant_id || ''}:${provider}:${external || booking.id}`;
    const current = groups.get(key);
    const bookingIds = booking.booking_ids || (booking.id && !booking.queue_kind ? [booking.id] : []);
    const ids = [...new Set([...(current?.booking_ids || []), ...bookingIds])];
    groups.set(key, {
      ...(current || booking), id: key, queue_kind: 'mapping_required', provider,
      booking_ids: ids, duplicate_hold_count: Math.max(0, ids.length - 1),
      action_url: current?.action_url || booking.action_url || (['exely', 'hotelrunner'].includes(provider) ? `/${provider}` : '/channel-manager'),
    });
  }
  return [...groups.values()];
}
