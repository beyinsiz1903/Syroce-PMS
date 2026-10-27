import { describe, expect, it } from 'vitest';
import { exelyReservationDetails } from '../exelyReservation';

describe('exelyReservationDetails', () => {
  it('requires explicit Exely provenance, not just fields on another provider booking', () => {
    expect(exelyReservationDetails({ booking_source: 'hotelrunner', provider_channel_name: 'Liberty Channel' })).toBeNull();
  });
  it('preserves independent references, de-duplicates and ignores malformed values', () => {
    expect(exelyReservationDetails({ source: { provider: 'exely' }, provider_group_reservation_id: 'exely',
      channel_reservation_id: 'channel', channel_reservation_ids: ['channel', 'second', null, { id: 'bad' }],
      provider_payment_method: { value: 'bad' }, payment_method: 'BankCardGuarantee' })).toEqual({
      channel: '', reservationId: 'exely', channelReservationIds: ['channel', 'second'], paymentMethod: 'BankCardGuarantee',
    });
  });
});
