import assert from 'node:assert/strict';
import test from 'node:test';
import {
  CalendarDataError,
  calendarDataReady,
  verifiedRoomBlocks,
  loadCalendarReservationPages,
  type CalendarDataFailure,
  type CalendarPageParams,
  type CalendarQueryState,
} from '../calendarData';

function booking(id: number | string) {
  return { id: String(id), room_id: `room-${id}`, check_in: '2026-10-10', check_out: '2026-10-20' };
}

const hasReason = (reason: CalendarDataFailure) => (error: unknown) =>
  error instanceof CalendarDataError && error.reason === reason;

test('calendar reads every overlapping page, including reservations beyond recent 50', async () => {
  const records = Array.from({ length: 451 }, (_, index) => booking(index));
  const calls: CalendarPageParams[] = [];
  const result = await loadCalendarReservationPages(async (params) => {
    calls.push(params);
    return records.slice(params.offset, params.offset + params.limit);
  }, '2026-10-12', '2026-10-19');

  assert.equal(result.length, 451);
  assert.equal(result.at(-1)?.id, '450');
  assert.deepEqual(calls, [0, 200, 400].map((offset) => ({
    start_date: '2026-10-12', end_date: '2026-10-19', limit: 200, offset,
  })));
});

test('calendar preserves stays crossing either overlap boundary and exclusive end parameter', async () => {
  const spanning = [
    { ...booking('left'), check_in: '2026-10-01', check_out: '2026-10-13' },
    { ...booking('right'), check_in: '2026-10-18', check_out: '2026-11-01' },
  ];
  const result = await loadCalendarReservationPages(async (params) => {
    assert.equal(params.start_date, '2026-10-12');
    assert.equal(params.end_date, '2026-10-19');
    assert.equal('check_in' in params, false);
    assert.equal('check_out' in params, false);
    return spanning;
  }, '2026-10-12', '2026-10-19');
  assert.deepEqual(result, spanning);
});

test('calendar confirms a full final page with another request and accepts a real empty result', async () => {
  const offsets: number[] = [];
  const result = await loadCalendarReservationPages(async ({ offset }) => {
    offsets.push(offset);
    return offset === 0 ? [booking('a'), booking('b')] : [];
  }, '2026-10-12', '2026-10-19', { pageSize: 2 });
  assert.equal(result.length, 2);
  assert.deepEqual(offsets, [0, 2]);
  assert.deepEqual(await loadCalendarReservationPages(async () => [], '2026-10-12', '2026-10-19'), []);
});

test('calendar rejects malformed payloads and rows instead of presenting partial inventory', async () => {
  const invalidPages: unknown[] = [
    null, undefined, { bookings: [] }, [null], [{}], [{ ...booking('a'), id: '' }],
    [{ ...booking('a'), check_in: '2026-02-30' }],
    [{ ...booking('a'), check_out: 'bad-date' }],
    [{ ...booking('a'), room_id: 42 }],
  ];
  for (const page of invalidPages) {
    await assert.rejects(loadCalendarReservationPages(async () => page, '2026-10-12', '2026-10-19'), hasReason('invalid_page'));
  }
  await assert.rejects(loadCalendarReservationPages(async ({ offset }) => offset === 0
    ? [booking('a'), booking('b')] : { bookings: [] }, '2026-10-12', '2026-10-19', { pageSize: 2 }), hasReason('invalid_page'));
});

test('calendar rejects repeated pages and duplicate bookings within a page', async () => {
  await assert.rejects(loadCalendarReservationPages(async () => [booking('a'), booking('b')], '2026-10-12', '2026-10-19', { pageSize: 2 }), hasReason('duplicate_booking'));
  await assert.rejects(loadCalendarReservationPages(async () => [booking('a'), booking('a')], '2026-10-12', '2026-10-19'), hasReason('duplicate_booking'));
});

test('calendar page cap and later network errors never resolve a partial array', async () => {
  let requests = 0;
  await assert.rejects(loadCalendarReservationPages(async ({ offset }) => {
    requests += 1;
    return [booking(offset), booking(offset + 1)];
  }, '2026-10-12', '2026-10-19', { pageSize: 2, maxPages: 2 }), hasReason('page_limit'));
  assert.equal(requests, 2);
  const failure = new Error('network unavailable');
  await assert.rejects(loadCalendarReservationPages(async ({ offset }) => {
    if (offset > 0) throw failure;
    return [booking('a'), booking('b')];
  }, '2026-10-12', '2026-10-19', { pageSize: 2 }), (error) => error === failure);
});

test('calendar rejects invalid ranges before fetching', async () => {
  for (const [start, end] of [['2026-02-30', '2026-03-10'], ['2026-10-12', '2026-10-12'], ['2026-10-19', '2026-10-12']]) {
    await assert.rejects(loadCalendarReservationPages(async () => {
      assert.fail('invalid range must not fetch');
    }, start, end), hasReason('invalid_range'));
  }
});

test('calendar availability needs both successful current-window lists and a connection', () => {
  const ready: CalendarQueryState = { data: [], isPending: false, isError: false, fetchStatus: 'idle' };
  assert.equal(calendarDataReady(true, [ready, ready]), true);
  assert.equal(calendarDataReady(false, [ready, ready]), false);
  assert.equal(calendarDataReady(true, [ready, { ...ready, isPending: true }]), false);
  assert.equal(calendarDataReady(true, [ready, { ...ready, isError: true }]), false);
  assert.equal(calendarDataReady(true, [ready, { ...ready, isPlaceholderData: true }]), false);
  assert.equal(calendarDataReady(true, [ready, { ...ready, fetchStatus: 'paused' }]), false);
  assert.equal(calendarDataReady(true, [ready, { ...ready, fetchStatus: 'fetching' }]), false);
  assert.equal(calendarDataReady(true, [ready, { ...ready, data: undefined }]), false);
  assert.equal(calendarDataReady(true, []), false);
});

test('block reads accept real empty results and normalize full datetime boundaries', () => {
  assert.deepEqual(verifiedRoomBlocks({ blocks: [], count: 0 }), []);
  const block = { id: 'b', room_id: 'r', start_date: '2026-10-16T00:00:00Z', end_date: '2026-10-18T11:00:00Z' };
  assert.deepEqual(verifiedRoomBlocks([block]), [{ ...block, start_date: '2026-10-16', end_date: '2026-10-18' }]);
});

test('block reads reject malformed, duplicate, incomplete and capped payloads', () => {
  const block = { id: 'b', room_id: 'r', start_date: '2026-10-16', end_date: null };
  for (const payload of [{}, null, { blocks: [], count: 1 }, [null], [{ ...block, room_id: '' }],
    [{ ...block, start_date: '2026-02-30' }], [block, block], Array.from({ length: 1000 }, (_, i) => ({ ...block, id: String(i) }))]) {
    assert.throws(() => verifiedRoomBlocks(payload), hasReason('invalid_page'));
  }
});
