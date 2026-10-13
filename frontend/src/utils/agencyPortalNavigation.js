export const AGENCY_ADMIN_RETURN_PATH = '/admin/agencies';

export function agencyVoucherPath(portalMode, reservationId, email = false) {
  if (!reservationId) throw new Error('Rezervasyon kimliği eksik');
  if (!['marketplace', 'hotel'].includes(portalMode)) throw new Error('Portal türü doğrulanamadı');
  const prefix = portalMode === 'marketplace' ? '/marketplace/v1' : '/agency-portal';
  return `${prefix}/reservations/${encodeURIComponent(reservationId)}/${email ? 'voucher-email' : 'voucher.pdf'}`;
}
