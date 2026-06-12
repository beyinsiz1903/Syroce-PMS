import { describe, it, expect } from 'vitest';
import { buildKbsBody } from '@/lib/kbsExtensionBridge';

describe('buildKbsBody', () => {
  it('maps queue payload fields to the canonical KBS request body', () => {
    const payload = {
      guest_name: 'Ali Veli',
      nationality: 'TC',
      id_number: '12345678901',
      passport_number: '',
      birth_date: '1990-01-01',
      room_number: '101',
      check_in: '2026-06-12',
      check_out: '2026-06-14',
    };
    const body = buildKbsBody(payload, 'checkin');
    expect(body.action).toBe('checkin');
    expect(body.guest_name).toBe('Ali Veli');
    expect(body.id_number).toBe('12345678901');
    expect(body.birth_date).toBe('1990-01-01');
    expect(body.room_number).toBe('101');
    expect(body.check_in).toBe('2026-06-12');
    expect(body.check_out).toBe('2026-06-14');
  });

  it('defaults action to checkin and nationality to TC', () => {
    const body = buildKbsBody({ guest_name: 'X' });
    expect(body.action).toBe('checkin');
    expect(body.nationality).toBe('TC');
  });

  it('preserves an explicit nationality and checkout action', () => {
    const body = buildKbsBody({ nationality: 'DE' }, 'checkout');
    expect(body.action).toBe('checkout');
    expect(body.nationality).toBe('DE');
  });

  it('fills missing fields with empty strings (no undefined)', () => {
    const body = buildKbsBody({}, 'checkin');
    for (const v of Object.values(body)) {
      expect(typeof v).toBe('string');
    }
    expect(body.guest_name).toBe('');
    expect(body.passport_number).toBe('');
  });

  it('tolerates a null/undefined payload', () => {
    const body = buildKbsBody(undefined, 'checkin');
    expect(body.action).toBe('checkin');
    expect(body.guest_name).toBe('');
    expect(body.nationality).toBe('TC');
  });
});
