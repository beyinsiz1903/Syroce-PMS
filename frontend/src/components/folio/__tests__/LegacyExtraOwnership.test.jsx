import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import LegacyExtraOwnership from '../LegacyExtraOwnership';
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
const props = () => ({ bookingId: 'b', currency: 'TRY', onChanged: vi.fn(),
  folios: [{ id: 'original', folio_number: 'F410', status: 'open', currency: 'TRY' },
    { id: 'new', folio_number: 'F419', status: 'open', currency: 'TRY' },
    { id: 'closed', folio_number: 'FCLOSED', status: 'closed', currency: 'TRY' },
    { id: 'eur', folio_number: 'FEUR', status: 'open', currency: 'EUR' }],
  extras: [{ id: 'e1', description: 'Giriş minibar', amount: 120, currency: 'TRY' },
    { id: 'e2', description: 'Ara gün minibar', amount: 80, currency: 'TRY' },
    { id: 'e3', description: 'Çıkış minibar', amount: 60, currency: 'TRY' },
    { id: 'bound', description: 'Zaten bağlı', amount: 25, folio_id: 'original' },
    { id: 'void', description: 'İptal', amount: 10, voided: true }],
});
function choose() {
  for (const name of [/Giriş minibar/, /Ara gün minibar/, /Çıkış minibar/]) fireEvent.click(screen.getByRole('checkbox', { name }));
  fireEvent.change(screen.getByLabelText('Ek ücretlerin hesabı'), { target: { value: 'original' } });
  fireEvent.change(screen.getByLabelText('Hesap seçimi açıklaması'), { target: { value: 'Asıl misafir hesabına ait üç eski minibar' } });
}
beforeEach(() => post.mockReset().mockResolvedValue({ data: { success: true } }));
it('selects original source IDs and exact total without creating charge/payment', async () => {
  const p = props(); render(<LegacyExtraOwnership {...p} />);
  expect(screen.getByRole('button')).toBeDisabled();
  expect(screen.queryByText(/Zaten bağlı|İptal/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Ek ücretlerin hesabı')).not.toHaveTextContent('FCLOSED');
  expect(screen.getByLabelText('Ek ücretlerin hesabı')).not.toHaveTextContent('FEUR');
  choose();
  expect(screen.getByText(/Seçilen toplam:/)).toHaveTextContent('260');
  fireEvent.click(screen.getByRole('button'));
  await waitFor(() => expect(p.onChanged).toHaveBeenCalledOnce());
  expect(post).toHaveBeenCalledExactlyOnceWith('/folio-windows/assign-legacy-extras', {
    booking_id: 'b', target_folio_id: 'original', extra_ids: ['e1', 'e2', 'e3'], expected_total: 260,
    currency: 'TRY', reason: 'Asıl misafir hesabına ait üç eski minibar', request_id: expect.any(String),
  });
});
it('retains one request key when a network result is uncertain', async () => {
  post.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ data: {} });
  render(<LegacyExtraOwnership {...props()} />); choose(); fireEvent.click(screen.getByRole('button'));
  await screen.findByRole('alert'); fireEvent.click(screen.getByRole('button'));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
});
it('never allows writes from read-only guest cards', () => {
  render(<LegacyExtraOwnership {...props()} readOnly />);
  expect(screen.getByRole('button')).toBeDisabled();
  for (const checkbox of screen.getAllByRole('checkbox')) expect(checkbox).toBeDisabled();
  expect(post).not.toHaveBeenCalled();
});
it('does not ask to resolve ownership while there is only one account', () => {
  const p = props(); render(<LegacyExtraOwnership {...p} folios={[p.folios[0]]} />);
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
