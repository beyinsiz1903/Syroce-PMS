import { describe, expect, it, vi } from 'vitest';
import { resolvePostLoginDestination } from '../postLoginWorkspace';

const chainAdmin = { role: 'admin', tenant_id: 'hotel-denizli' };

describe('resolvePostLoginDestination', () => {
  it('lands a chain manager on the hotel selector when multiple properties are authorised', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        data: {
          properties: [
            { property_id: 'hotel-denizli' },
            { property_id: 'hotel-fethiye' },
            { property_id: 'hotel-antalya' },
          ],
        },
      }),
    };

    await expect(resolvePostLoginDestination({ api, user: chainAdmin })).resolves.toBe('/app/multi-property');
    expect(api.get).toHaveBeenCalledOnce();
    expect(api.get).toHaveBeenCalledWith('/multi-property/properties');
  });

  it('preserves an explicit deep link without probing chain or onboarding state', async () => {
    const api = { get: vi.fn() };

    await expect(resolvePostLoginDestination({
      api,
      user: chainAdmin,
      existingRedirect: '/app/reservation-calendar',
    })).resolves.toBe('/app/reservation-calendar');
    expect(api.get).not.toHaveBeenCalled();
  });

  it('keeps onboarding for a fresh standalone hotel', async () => {
    const api = {
      get: vi.fn()
        .mockResolvedValueOnce({ data: { properties: [{ property_id: 'hotel-denizli' }] } })
        .mockResolvedValueOnce({ data: { dismissed: false, completed: 1 } }),
    };

    await expect(resolvePostLoginDestination({ api, user: chainAdmin })).resolves.toBe('/app/onboarding');
  });
});
