import { beforeEach, describe, expect, it, vi } from 'vitest';

const { confirmDialog } = vi.hoisted(() => ({ confirmDialog: vi.fn() }));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

import {
  confirmUnifiedRateMutation,
  getUnifiedRateDeliveryFeedback,
} from '@/pages/UnifiedRateManager';

describe('UnifiedRateManager write safety', () => {
  beforeEach(() => confirmDialog.mockReset());

  it('requires explicit confirmation before a channel mutation', async () => {
    confirmDialog.mockResolvedValue(false);

    await expect(confirmUnifiedRateMutation({
      roomCount: 1,
      dateFrom: '2026-08-14',
      dateTo: '2026-08-15',
    })).resolves.toBe(false);
    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      variant: 'danger',
      confirmText: 'Güncellemeyi Başlat',
    }));
  });

  it.each(['SCHEDULED', 'QUEUED', 'PENDING'])(
    'never reports %s delivery as provider-verified success',
    deliveryState => {
      expect(getUnifiedRateDeliveryFeedback({
        saved: 2,
        provider_verified: false,
        provider_delivery_state: deliveryState,
      })).toEqual({
        level: 'warning',
        message: '2 yerel kayıt güncellendi; provider teslimatı henüz doğrulanmadı.',
      });
    },
  );

  it('reports success only for provider-confirmed delivery', () => {
    expect(getUnifiedRateDeliveryFeedback({
      saved: 10,
      provider_verified: true,
      provider_delivery_state: 'CONFIRMED',
    })).toEqual({
      level: 'success',
      message: '10 kayıt güncellendi ve provider teslimatı doğrulandı.',
    });
  });
});
