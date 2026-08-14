import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import FolioDetailView from '@/pages/FolioDetailView';

const { get, post, axiosMock, translate } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  const translate = (key) => key;
  return {
    get,
    post,
    translate,
    axiosMock: { get, post },
  };
});

vi.mock('axios', () => ({ default: axiosMock }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: translate }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const folioId = 'cb6d687f-7011-43f6-8dd6-570c36fc8936';
const paymentId = 'a317e942-fd3b-43be-8ad0-7dc552db01fd';
const detail = {
  folio: {
    id: folioId,
    folio_number: 'F-TEST',
    status: 'open',
    folio_type: 'guest',
    booking_id: '69e04333-0000-4000-8000-000000000000',
  },
  summary: {
    total_charges: 3955,
    charge_count: 3,
    total_payments: 7455,
    payment_count: 3,
    balance: -3500,
    voided_charges: 0,
    voided_payments: 0,
  },
  timeline: [{
    id: paymentId,
    type: 'payment',
    description: 'CASH',
    method: 'cash',
    amount: 35,
    timestamp: '2026-08-14T05:44:48Z',
    running_balance: -3500,
    voided: false,
  }],
};

describe('FolioDetailView payment void', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({ data: detail });
    post.mockResolvedValue({ data: { success: true } });
  });

  afterEach(() => cleanup());

  it('requires a reason and PIN, then sends one verified void request', async () => {
    render(
      <MemoryRouter>
        <FolioDetailView folioId={folioId} />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'İade' }));

    const confirm = screen.getByRole('button', { name: 'İadeyi Onayla' });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText('İade Nedeni *'), {
      target: { value: 'Yanlış tutar düzeltmesi' },
    });
    fireEvent.change(screen.getByLabelText('Yetkili PIN *'), {
      target: { value: 'test-pin' },
    });
    fireEvent.click(confirm);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post).toHaveBeenNthCalledWith(
      1,
      '/cashier/peer-verify',
      { pin: 'test-pin' },
      { _skipAuthRetry: true },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      `/folio/${folioId}/payment/${paymentId}/void`,
      { reason: 'Yanlış tutar düzeltmesi' },
    );
    expect(get).toHaveBeenLastCalledWith(
      `/pms-core/folio/detail/${folioId}`,
      { headers: {} },
    );
  });

  it('does not offer a second void action for an already voided payment', async () => {
    get.mockResolvedValue({
      data: {
        ...detail,
        timeline: [{ ...detail.timeline[0], voided: true }],
      },
    });

    render(
      <MemoryRouter>
        <FolioDetailView folioId={folioId} />
      </MemoryRouter>,
    );

    await screen.findByText('CASH');
    expect(screen.queryByRole('button', { name: 'İade' })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('does not submit a void when peer PIN verification is rejected', async () => {
    post.mockRejectedValueOnce({
      response: { status: 401, data: { detail: 'PIN hatalı' } },
    });

    render(
      <MemoryRouter>
        <FolioDetailView folioId={folioId} />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'İade' }));
    fireEvent.change(screen.getByLabelText('İade Nedeni *'), {
      target: { value: 'Yanlış tutar düzeltmesi' },
    });
    fireEvent.change(screen.getByLabelText('Yetkili PIN *'), {
      target: { value: 'wrong-pin' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'İadeyi Onayla' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith(
      '/cashier/peer-verify',
      { pin: 'wrong-pin' },
      { _skipAuthRetry: true },
    );
    expect(screen.getByRole('dialog', { name: 'Ödeme İadesi' })).toBeInTheDocument();
    expect(screen.getByLabelText('Yetkili PIN *')).toHaveValue('');
  });
});
