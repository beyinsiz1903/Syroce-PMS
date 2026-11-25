import type { QueryClient } from '@tanstack/react-query';

/** Refresh read models only; never replay a payment when returning to a stay. */
export async function refreshReservationReads(client: QueryClient, bookingId: string): Promise<void> {
  if (!bookingId) return;
  await Promise.allSettled(['reservation-full', 'reservation-enhanced', 'reservation-ota'].map(key =>
    client.refetchQueries({ queryKey: [key, bookingId], exact: true, type: 'all' }),
  ));
}
