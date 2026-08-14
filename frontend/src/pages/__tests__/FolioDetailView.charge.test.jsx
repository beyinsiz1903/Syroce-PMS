import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import FolioDetailView from '@/pages/FolioDetailView';

const { get, post, axiosMock } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  return { get, post, axiosMock: { get, post } };
});

vi.mock('axios', () => ({ default: axiosMock }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const folioId = 'cb6d687f-7011-43f6-8dd6-570c36fc8936';
const detail = (status) => ({
  folio: {
    id: folioId,
    folio_number: 'F-TEST',
    status,
    folio_type: 'guest',
    booking_id: '69e04333-0000-4000-8000-000000000000',
  },
  summary: {
    total_charges: 0,
    charge_count: 0,
    total_payments: 0,
    payment_count: 0,
    balance: 0,
    voided_charges: 0,
    voided_payments: 0,
  },
  timeline: [],
});

describe('FolioDetailView charge contract', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  afterEach(() => cleanup());

  it('does not offer charge posting for a closed folio', async () => {
    get.mockResolvedValue({ data: detail('closed') });

    render(<MemoryRouter><FolioDetailView folioId={folioId} /></MemoryRouter>);

    expect(await screen.findByRole('button', { name: 'Masraf Ekle' })).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
  });

  it('posts to the exact open folio with idempotency and confirms the write', async () => {
    get.mockResolvedValue({ data: detail('open') });
    post.mockResolvedValue({ data: { id: 'charge-1' } });

    render(<MemoryRouter><FolioDetailView folioId={folioId} /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Masraf Ekle' }));
    fireEvent.change(screen.getByPlaceholderText('Minibar - Kola vb.'), {
      target: { value: 'Test masrafı' },
    });
    const spinbuttons = screen.getAllByRole('spinbutton');
    fireEvent.change(spinbuttons[0], { target: { value: '10' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Masraf Ekle' }).at(-1));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe(`/folio/${folioId}/charge`);
    expect(post.mock.calls[0][1]).toMatchObject({
      description: 'Test masrafı',
      amount: 10,
      quantity: 1,
    });
    expect(post.mock.calls[0][2].headers['Idempotency-Key']).toBeTruthy();
  });
});
