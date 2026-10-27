import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import FolioPrintOptions from '../FolioPrintOptions';

afterEach(cleanup);
const props = {
  folios: [{ id: 'g', folio_type: 'guest', currency: 'USD', balance: 638.8, folio_number: 'F-G' }, { id: 'a', folio_type: 'agency', currency: 'USD', balance: 9900, folio_number: 'F-A' }],
  charges: [
    { id: 'food', folio_id: 'g', category: 'food', description: 'Akşam yemeği', total: 12, service_date: '2026-10-24', service_time: '19:30' },
    { id: 'room', folio_id: 'g', category: 'room', description: 'Gizli konaklama bedeli', total: 560 },
    { id: 'agency', folio_id: 'a', category: 'room', description: 'Gizli acente bedeli', total: 9900 },
    { id: 'spa', folio_id: 'g', category: 'spa', description: 'Masaj', total: 30 },
  ],
  extraCharges: [], payments: [{ id: 'p', folio_id: 'g', amount: 300 }],
  booking: { id: 'demo', guest_name: 'Deniz Kaya', currency: 'USD', total_amount: 99999, room_number: '104', hotel_name: 'Örnek Otel' },
  guest: { name: 'Deniz Kaya' }, room: { room_number: '104' },
};

it('a food-only preview contains no room/agency prices, global balance or payments', () => {
  render(<FolioPrintOptions {...props} currentFolioId="a" />);
  expect(screen.getByLabelText('Çıktı alıcısı')).toHaveValue('guest');
  expect(screen.queryByRole('option', { name: /F-A/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Hizmet kapsamı'), { target: { value: 'food_beverage' } });
  fireEvent.click(screen.getByRole('button', { name: 'Çıktıyı önizle' }));
  const preview = within(screen.getByRole('dialog', { name: 'Folyo yazdırma önizlemesi' }));
  expect(preview.getByText('Akşam yemeği')).toBeInTheDocument();
  expect(preview.getByText('24.10.2026 · 19:30')).toBeInTheDocument();
  expect(preview.queryByText(/Gizli|Masaj|638|9.900|99.999|560,00|300,00/)).not.toBeInTheDocument();
  expect(preview.queryByText(/Kalan bakiye|Net tahsilat|Tahsilatlar/)).not.toBeInTheDocument();
  expect(preview.getByText(/Fatura veya mali belge değildir/)).toBeInTheDocument();
});

it('can select one account and then deselect individual services', () => {
  render(<FolioPrintOptions {...props} />);
  fireEvent.change(screen.getByLabelText('Yazdırılacak hesap'), { target: { value: 'g' } });
  fireEvent.click(screen.getByRole('checkbox', { name: /Gizli konaklama bedeli/ }));
  fireEvent.click(screen.getByRole('checkbox', { name: /Masaj/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Çıktıyı önizle' }));
  const dialog = screen.getByRole('dialog');
  expect(dialog).toHaveTextContent('Seçili Hizmetler Dökümü');
  expect(dialog).not.toHaveTextContent('Gizli konaklama bedeli');
  expect(dialog).not.toHaveTextContent('Kalan bakiye');
});

it('allows a migrated opening-balance statement without fabricating charges', () => {
  render(<FolioPrintOptions {...props} charges={[]} payments={[]} folios={[{ ...props.folios[0], opening_balance: 40 }]} />);
  expect(screen.getByRole('button', { name: 'Çıktıyı önizle' })).toBeEnabled();
});

it('blocks a mixed-currency total rather than treating it as one currency', () => {
  render(<FolioPrintOptions {...props} charges={[...props.charges, { id: 'fx', folio_id: 'g', currency: 'EUR', total: 50 }]} />);
  expect(screen.getByRole('button', { name: 'Çıktıyı önizle' })).toBeDisabled();
});
