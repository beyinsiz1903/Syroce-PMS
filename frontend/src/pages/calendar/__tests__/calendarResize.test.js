import { describe, expect, it } from 'vitest';

import { checkoutAfterCalendarNight, validateStayResize } from '../calendarHelpers';

describe('calendar stay resize', () => {
  const booking = {
    id: 'booking-1',
    status: 'confirmed',
    check_in: '2026-09-10',
    check_out: '2026-09-12',
  };

  it('treats the dropped cell as the final occupied night', () => {
    expect(checkoutAfterCalendarNight('2026-09-13')).toBe('2026-09-14');
  });

  it('extends checkout using an exclusive checkout date', () => {
    expect(validateStayResize(booking, '2026-09-13')).toEqual({
      ok: true,
      newCheckOut: '2026-09-14',
      extending: true,
    });
  });

  it('shortens a stay without allowing checkout on or before check-in', () => {
    expect(validateStayResize(booking, '2026-09-10')).toEqual({
      ok: true,
      newCheckOut: '2026-09-11',
      extending: false,
    });
    expect(validateStayResize(booking, '2026-09-09')).toMatchObject({ ok: false });
  });

  it('does not modify completed stays or dates before the business boundary', () => {
    expect(validateStayResize({ ...booking, status: 'checked_out' }, '2026-09-13')).toMatchObject({ ok: false });
    expect(validateStayResize(booking, '2026-09-10', '2026-09-12')).toMatchObject({ ok: false });
  });

  it('recognizes dropping on the existing final night as unchanged', () => {
    expect(validateStayResize(booking, '2026-09-11')).toEqual({ ok: false, unchanged: true });
  });
});
