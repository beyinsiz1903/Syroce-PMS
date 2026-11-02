import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const { confirmDialog } = vi.hoisted(() => ({ confirmDialog: vi.fn() }));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

import {
  confirmUnifiedRateMutation,
  getUnifiedRateDeliveryFeedback,
  verifiedProviderChannels,
  providerWriteNotice,
  RateDeliveryReceipt,
} from '@/pages/UnifiedRateManager';

describe('UnifiedRateManager write safety', () => {
  beforeEach(() => confirmDialog.mockReset());

  it('names the blocked provider instead of always blaming HotelRunner', () => {
    const message = providerWriteNotice([{ name: 'Exely', mode: 'read_only', block_reason: 'EXELY_ARI_WRITE_DISABLED' }]);
    expect(message).toContain('Exely');
    expect(message).toContain('EXELY_ARI_WRITE_DISABLED');
    expect(message).not.toContain('HotelRunner');
  });

  it('keeps the delivery result visible after the toast disappears', () => {
    render(<RateDeliveryReceipt receipt={{ data: { saved: 16, provider_verified: true, provider_delivery_state: 'CONFIRMED' }, dateFrom: '2026-11-02', dateTo: '2026-11-09', roomCount: 2, fields: ['availability'] }} />);
    expect(screen.getByTestId('rate-delivery-receipt')).toHaveTextContent('CONFIRMED');
    expect(screen.getByTestId('rate-delivery-receipt')).toHaveTextContent('2026-11-02 – 2026-11-09');
  });

  it('does not turn a lost response into a safe retry claim', () => {
    const feedback = getUnifiedRateDeliveryFeedback({ provider_delivery_state: 'UNKNOWN' });
    expect(feedback.level).toBe('warning');
    expect(feedback.message).toContain('uzlaştırın');
    expect(feedback.message).not.toContain('0 kayıt');
  });

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

  it('says agency-only updates skip the channel manager and names the sale currency', async () => {
    confirmDialog.mockResolvedValue(true);

    await confirmUnifiedRateMutation({
      roomCount: 1, dateFrom: '2026-11-20', dateTo: '2026-11-22', agenciesOnly: true, currency: 'TRY',
    });
    const { message } = confirmDialog.mock.calls[0][0];
    expect(message).toContain('TRY');
    expect(message).toContain('kanal yöneticisine ve otel takvimine gönderilmeyecek');
    expect(message).not.toContain('bağlı kanallara');
  });

  it('never exposes disconnected or stale provider channels as push targets', () => {
    const channels = [{ code: 'booking', name: 'Booking.com' }];
    expect(verifiedProviderChannels({ connected: false, channels })).toEqual([]);
    expect(verifiedProviderChannels({ connected: true, channels_stale: true, channels })).toEqual([]);
    expect(verifiedProviderChannels({ connected: true, channels_stale: false, channels })).toEqual(channels);
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
        message: '2 yerel kayıt güncellendi; kanal sağlayıcısına teslimat henüz doğrulanmadı.',
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
      message: '10 kayıt güncellendi ve kanal sağlayıcısına teslimat doğrulandı.',
    });
  });

  it('reports an OTA-independent agency delivery as completed', () => {
    expect(getUnifiedRateDeliveryFeedback({
      saved: 4,
      provider: 'agency',
      agency_push_count: 2,
    })).toEqual({
      level: 'success',
      message: '4 kayıt güncellendi ve 2 acenteye anında iletildi.',
    });
  });

  it('makes partial and rejected provider deliveries visible', () => {
    expect(getUnifiedRateDeliveryFeedback({ saved: 3, provider_delivery_state: 'PARTIAL' }).level).toBe('error');
    expect(getUnifiedRateDeliveryFeedback({
      saved: 3,
      provider_delivery_state: 'NOT_SENT',
      provider_error_codes: ['EXELY_ARI_REJECTED'],
    })).toEqual({
      level: 'error',
      message: '3 yerel kayıt güncellendi; kanal sağlayıcısına teslimat başarısız: EXELY_ARI_REJECTED',
    });
  });
});
