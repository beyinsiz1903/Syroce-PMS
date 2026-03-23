import { DAYS, UPDATE_FIELDS, CHANNELS } from '../constants';

describe('rate-manager/constants', () => {
  describe('DAYS', () => {
    it('has all 7 days of the week', () => {
      expect(DAYS).toHaveLength(7);
    });

    it('starts with Pazar (Sunday = 0) and ends with Cumartesi (Saturday = 6)', () => {
      expect(DAYS[0]).toEqual({ value: 0, label: 'Pazar' });
      expect(DAYS[6]).toEqual({ value: 6, label: 'Cumartesi' });
    });

    it('has sequential values 0-6', () => {
      DAYS.forEach((day, idx) => {
        expect(day.value).toBe(idx);
      });
    });

    it('each day has a label string', () => {
      DAYS.forEach((day) => {
        expect(typeof day.label).toBe('string');
        expect(day.label.length).toBeGreaterThan(0);
      });
    });
  });

  describe('UPDATE_FIELDS', () => {
    it('has expected fields', () => {
      const keys = UPDATE_FIELDS.map((f) => f.key);
      expect(keys).toContain('availability');
      expect(keys).toContain('rate');
      expect(keys).toContain('min_stay');
      expect(keys).toContain('max_stay');
      expect(keys).toContain('cta');
      expect(keys).toContain('ctd');
      expect(keys).toContain('stop_sell');
    });

    it('each field has key and label', () => {
      UPDATE_FIELDS.forEach((field) => {
        expect(field).toHaveProperty('key');
        expect(field).toHaveProperty('label');
        expect(typeof field.key).toBe('string');
        expect(typeof field.label).toBe('string');
      });
    });
  });

  describe('CHANNELS', () => {
    it('has at least 10 channels', () => {
      expect(CHANNELS.length).toBeGreaterThanOrEqual(10);
    });

    it('includes major OTAs', () => {
      const keys = CHANNELS.map((c) => c.key);
      expect(keys).toContain('booking_com');
      expect(keys).toContain('expedia');
      expect(keys).toContain('airbnb');
    });

    it('each channel has key and label', () => {
      CHANNELS.forEach((channel) => {
        expect(channel).toHaveProperty('key');
        expect(channel).toHaveProperty('label');
        expect(typeof channel.key).toBe('string');
        expect(typeof channel.label).toBe('string');
      });
    });

    it('has no duplicate keys', () => {
      const keys = CHANNELS.map((c) => c.key);
      expect(new Set(keys).size).toBe(keys.length);
    });
  });
});
