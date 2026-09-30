import { describe, expect, it, vi } from 'vitest';

import { recordInitialPrepayment } from '../prepayment';

const paymentResponse = (overrides = {}) => ({
  data: {
    payment: {
      id: 'payment-1',
      booking_id: 'booking-1',
      payment_type: 'prepayment',
      amount: 1000,
      ...overrides,
    },
  },
});

describe('calendar reservation prepayment', () => {
  it('records a currency-complete prepayment and verifies the durable response', async () => {
    const client = { post: vi.fn().mockResolvedValue(paymentResponse()) };

    await expect(recordInitialPrepayment({
      client,
      bookingId: 'booking-1',
      amount: 1000,
      method: 'bank_transfer',
      currency: 'TL',
      idempotencyKey: 'create-1',
    })).resolves.toEqual(expect.objectContaining({ id: 'payment-1' }));

    expect(client.post).toHaveBeenCalledWith(
      '/pms/reservations/booking-1/record-payment',
      expect.objectContaining({
        amount: 1000,
        method: 'bank_transfer',
        payment_type: 'prepayment',
        currency: 'TRY',
        received_currency: 'TRY',
        received_amount: 1000,
        exchange_rate: 1,
      }),
    );
  });

  it('retries an uncertain network response with the same idempotent reference', async () => {
    const client = {
      post: vi.fn()
        .mockRejectedValueOnce(new Error('network lost'))
        .mockResolvedValueOnce(paymentResponse()),
    };

    await recordInitialPrepayment({
      client,
      bookingId: 'booking-1',
      amount: 1000,
      method: 'bank_transfer',
      currency: 'TRY',
      idempotencyKey: 'create-1',
    });

    expect(client.post).toHaveBeenCalledTimes(2);
    expect(client.post.mock.calls[0][1].reference).toBe(client.post.mock.calls[1][1].reference);
  });

  it('rejects a success response that does not contain the requested payment', async () => {
    const client = { post: vi.fn().mockResolvedValue({ data: { success: true } }) };

    await expect(recordInitialPrepayment({
      client,
      bookingId: 'booking-1',
      amount: 1000,
      method: 'bank_transfer',
      currency: 'TRY',
      idempotencyKey: 'create-1',
    })).rejects.toThrow('Ön ödeme sunucu tarafından doğrulanamadı');
  });
});

