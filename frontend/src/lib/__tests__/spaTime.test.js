import { describe, expect, it } from 'vitest';
import { formatSpaTime, spaDateTimeInput, spaTimeZone, spaWallTimeToUtc } from '../spaTime';

describe('SPA hotel timezone conversion', () => {
  it.each([
    ['Europe/Istanbul', '2026-11-08T12:23', '2026-11-08T09:23:00.000Z'],
    ['America/New_York', '2026-11-08T12:23', '2026-11-08T17:23:00.000Z'],
    ['Asia/Kolkata', '2026-11-08T12:23', '2026-11-08T06:53:00.000Z'],
    ['Asia/Kathmandu', '2026-11-08T12:23', '2026-11-08T06:38:00.000Z'],
    ['UTC', '2026-11-08T12:23', '2026-11-08T12:23:00.000Z'],
    ['Europe/Istanbul', '2026-11-09T01:30', '2026-11-08T22:30:00.000Z'],
    ['Europe/Berlin', '2026-07-10T12:00', '2026-07-10T10:00:00.000Z'],
  ])('round-trips %s %s without using the browser timezone', (zone, wall, utc) => {
    expect(spaWallTimeToUtc(wall, zone)).toBe(utc);
    expect(spaDateTimeInput(new Date(utc), zone)).toBe(wall);
  });

  it.each([
    ['Europe/Berlin', '2026-03-29T02:30', /mevcut değil/],
    ['Europe/Berlin', '2026-10-25T02:30', /iki kez/],
    ['America/New_York', '2026-03-08T02:30', /mevcut değil/],
    ['America/New_York', '2026-11-01T01:30', /iki kez/],
  ])('rejects ambiguous or nonexistent wall time in %s at %s', (zone, wall, error) => {
    expect(() => spaWallTimeToUtc(wall, zone)).toThrow(error);
  });

  it.each(['', 'bad', '2026-02-30T10:00', '2026-11-08T24:00', '2026-11-08T12:00Z', '2026-11-08'])('does not silently normalize invalid input %s', (wall) => {
    expect(() => spaWallTimeToUtc(wall, 'Europe/Istanbul')).toThrow(/Geçerli/);
  });

  it.each([null, undefined, '', 'Mars/Unknown'])('does not invent a hotel timezone from %s', (zone) => {
    expect(spaTimeZone(zone)).toBeNull();
    expect(spaDateTimeInput(new Date(), zone)).toBe('');
    expect(() => spaWallTimeToUtc('2026-11-08T12:00', zone)).toThrow(/saat dilimi/);
  });

  it.each(['2026-11-08T09:00:00', '2026-11-08T09:00:00Z', '2026-11-08T12:00:00+03:00'])('renders legacy and offset instant %s only once in hotel time', (value) => {
    expect(formatSpaTime(value, 'Europe/Istanbul')).toBe('08.11 12:00');
  });

  it.each([null, '', 'invalid', '2026-11-08', new Date('invalid')])('renders missing/malformed instant %s as unavailable', (value) => {
    expect(formatSpaTime(value, 'Europe/Istanbul')).toBe('—');
  });
});
