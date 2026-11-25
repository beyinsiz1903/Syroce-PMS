import assert from 'node:assert/strict';
import test from 'node:test';
import { QueryClient } from '@tanstack/react-query';
import { refreshReservationReads } from '../reservationRefresh';

test('a web refund replaces cached native account reads without replaying a payment', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  let paid = 20;
  const calls: string[] = [];
  for (const key of ['reservation-full', 'reservation-enhanced', 'reservation-ota']) {
    await client.fetchQuery({ queryKey: [key, 'booking'], queryFn: async () => { calls.push(key); return { paid, due: 1320 - paid }; } });
  }
  await client.fetchQuery({ queryKey: ['reservation-full', 'other'], queryFn: async () => { calls.push('other'); return 'unchanged'; } });
  paid = 0; // Original receipt refunded through the web guest card.
  calls.length = 0;
  await refreshReservationReads(client, 'booking');
  assert.deepEqual(client.getQueryData(['reservation-full', 'booking']), { paid: 0, due: 1320 });
  assert.deepEqual(calls.sort(), ['reservation-enhanced', 'reservation-full', 'reservation-ota']);
  assert.equal(client.getQueryData(['reservation-full', 'other']), 'unchanged');
  client.clear();
});

test('an unavailable read does not prevent the other reads refreshing', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  let offline = false;
  await client.fetchQuery({ queryKey: ['reservation-enhanced', 'booking'], queryFn: async () => { if (offline) throw Error('offline'); return 1; } });
  let due = 1300;
  await client.fetchQuery({ queryKey: ['reservation-full', 'booking'], queryFn: async () => due });
  offline = true;
  due = 1320;
  await refreshReservationReads(client, 'booking');
  assert.equal(client.getQueryData(['reservation-full', 'booking']), 1320);
  await refreshReservationReads(client, '');
  client.clear();
});
