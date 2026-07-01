import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setCache, getCache } from '../cacheUtils';

describe('cacheUtils', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  describe('setCache', () => {
    it('stores data in localStorage with prefix', () => {
      setCache('test_key', { foo: 'bar' });
      const stored = localStorage.getItem('hotel_pms_cache_test_key');
      expect(stored).not.toBeNull();
      const parsed = JSON.parse(stored);
      expect(parsed.data).toEqual({ foo: 'bar' });
      expect(parsed.timestamp).toBeGreaterThan(0);
      expect(parsed.ttl).toBe(5 * 60 * 1000);
    });

    it('stores with custom TTL', () => {
      setCache('ttl_key', 'value', 10000);
      const parsed = JSON.parse(localStorage.getItem('hotel_pms_cache_ttl_key'));
      expect(parsed.ttl).toBe(10000);
    });

    it('handles localStorage errors gracefully', () => {
      const spy = vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem').mockImplementation(() => {
        throw new Error('QuotaExceeded');
      });
      expect(() => setCache('key', 'val')).not.toThrow();
      spy.mockRestore();
    });
  });

  describe('getCache', () => {
    it('returns cached data when valid', () => {
      setCache('valid', { result: 42 });
      const result = getCache('valid');
      expect(result).toEqual({ result: 42 });
    });

    it('returns null for missing key', () => {
      expect(getCache('nonexistent')).toBeNull();
    });

    it('returns null and removes expired entry', () => {
      const cacheKey = 'hotel_pms_cache_expired';
      const cacheData = {
        data: 'old',
        timestamp: Date.now() - 600000,
        ttl: 300000,
      };
      localStorage.setItem(cacheKey, JSON.stringify(cacheData));
      expect(getCache('expired')).toBeNull();
      expect(localStorage.getItem(cacheKey)).toBeNull();
    });

    it('handles corrupted localStorage data', () => {
      localStorage.setItem('hotel_pms_cache_corrupt', 'not json');
      expect(getCache('corrupt')).toBeNull();
    });
  });
});
