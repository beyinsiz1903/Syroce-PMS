import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { PaymentsSection } from '../OperationsSection';
import { reportPaymentMethodLabel } from '@/lib/reportPaymentLabels';

afterEach(cleanup);
it('explains non-cash settlements in the payment movement table without changing signed amounts', () => {
  const methods = ['gift_card_redemption', 'wallet', 'loyalty_redemption', 'barter', 'write_off'];
  render(<PaymentsSection reportDate="2026-11-12" paymentData={[]} payments={{ total_paid: 0, rows: methods.map((method, i) => ({ id: method, method, amount: i === 1 ? -30 : 10, currency: 'TRY' })) }} />);
  for (const label of ['Hediye kartı mahsubu', 'Cüzdan mahsubu', 'Sadakat puanı mahsubu', 'Barter (tahsilat değil)', 'Alacaktan silme (tahsilat değil)']) expect(screen.getByText(label)).toBeInTheDocument();
  expect(screen.queryByText('gift_card_redemption')).not.toBeInTheDocument();
  expect(screen.getByText(/-₺30,00/)).toBeInTheDocument();
});
it('uses shared labels for chart data while retaining ordinary and unknown methods', () => {
  expect(reportPaymentMethodLabel('wallet')).toBe('Cüzdan mahsubu');
  expect(reportPaymentMethodLabel('cash')).toBe('Nakit');
  expect(reportPaymentMethodLabel('debit_card')).toBe('Banka kartı');
  expect(reportPaymentMethodLabel('future_method')).toBe('future_method');
});
