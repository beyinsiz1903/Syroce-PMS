import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('@/api/axios', () => ({ default: { get: vi.fn().mockResolvedValue({ data: {} }) } }));

import axios from 'axios';
import ExelyPrepaymentSummary from '../ExelyPrepaymentSummary';
import { GeneralInfoTab } from '../InfoTabs';
import { OnlinePaymentTab } from '../OnlinePaymentTab';

const booking = (overrides = {}) => ({
  id: 'provider-prepaid', channel: 'exely', currency: 'USD', total_amount: 160,
  provider_group_reservation_id: 'provider-group', provider_booking_total: 460,
  provider_payment_method: 'BankCard',
  provider_prepayment: {
    schema_version: 1, scope: 'reservation', booking_total: 460, booking_currency: 'USD',
    remaining_amount: 300, overpayment_amount: 0,
    payments: [{ type: 'ReceivedPayment', amount: 160, currency: 'USD', payment_index: '0' }],
    totals: [{ currency: 'USD', received_amount: 160, expected_amount: 0, loyalty_amount: 0 }],
    ...overrides,
  },
});

describe('Exely provider prepayment', () => {
  beforeEach(() => axios.get.mockResolvedValue({ data: { has_vcc: false } }));

  it('shows provider receipt and services-inclusive remaining separately from local receipts', () => {
    render(<GeneralInfoTab booking={booking()} summary={{ balance: 160, total_payments: 0 }} payments={[]} />);
    const source = within(screen.getByTestId('exely-prepayment-summary'));
    expect(source.getByText('Alınan ön ödeme').parentElement).toHaveTextContent('160');
    expect(source.getByText('Exely rezervasyon bedeli').parentElement).toHaveTextContent('460');
    expect(source.getByText('Exely’de kalan tutar').parentElement).toHaveTextContent('300');
    expect(screen.getByText('Son tahsilat yöntemi').parentElement).toHaveTextContent('Tahsilat kaydı yok');
  });

  it('shows the prepayment in Online Payment even without a virtual card', async () => {
    render(<OnlinePaymentTab booking={booking()} readOnly />);
    expect(await screen.findByTestId('exely-prepayment-summary')).toHaveTextContent('Alınan ön ödeme160');
    expect(screen.getByTestId('online-payment-tab')).toHaveTextContent('Exely’de kalan tutar300');
  });

  it('does not let a card API error hide provider payment evidence', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'));
    render(<OnlinePaymentTab booking={booking()} readOnly />);
    expect(await screen.findByTestId('exely-prepayment-summary')).toHaveTextContent('160');
  });

  it('renders provider payment evidence while the independent card API is still loading', () => {
    axios.get.mockReturnValueOnce(new Promise(() => {}));
    render(<OnlinePaymentTab booking={booking()} readOnly />);
    expect(screen.getByTestId('exely-prepayment-summary')).toHaveTextContent('160');
    expect(screen.getByTestId('online-payment-loading')).toBeInTheDocument();
  });

  it('distinguishes pending and loyalty amounts from actual cash prepayment', () => {
    render(<ExelyPrepaymentSummary booking={booking({ remaining_amount: 440,
      totals: [{ currency: 'USD', received_amount: 0, expected_amount: 160, loyalty_amount: 20 }] })} />);
    expect(screen.getByText('Alınan ön ödeme').parentElement).toHaveTextContent('0');
    expect(screen.getByText('Beklenen ön ödeme (henüz alınmamış)').parentElement).toHaveTextContent('160');
    expect(screen.getByText('Kullanılan sadakat bakiyesi').parentElement).toHaveTextContent('20');
    expect(screen.getByText('Exely’de kalan tutar').parentElement).toHaveTextContent('440');
  });

  it('keeps mixed currencies separate and avoids an invented remaining amount', () => {
    render(<ExelyPrepaymentSummary booking={booking({ remaining_amount: null, overpayment_amount: null,
      totals: [{ currency: 'EUR', received_amount: 160, expected_amount: 0, loyalty_amount: 0 }] })} />);
    expect(screen.getByText('Alınan ön ödeme').parentElement).toHaveTextContent('EUR');
    expect(screen.getByText('Exely’de kalan tutar').parentElement).toHaveTextContent('Para birimleri farklı');
  });

  it('identifies group scope and overpayments without duplicating a per-room receipt', () => {
    render(<ExelyPrepaymentSummary booking={booking({ remaining_amount: 0, overpayment_amount: 40 })} />);
    expect(screen.getByTestId('exely-prepayment-summary')).toHaveTextContent('oda başına tekrar sayılmaz');
    expect(screen.getByText('Rezervasyon bedelini aşan ödeme').parentElement).toHaveTextContent('40');
  });

  it('does not describe legacy data or a bank-card guarantee as paid', () => {
    render(<ExelyPrepaymentSummary booking={{ channel: 'exely', payment_method: 'BankCardGuarantee' }} />);
    expect(screen.getByTestId('exely-prepayment-unknown')).toHaveTextContent('ön ödeme tutarı bulunmuyor');
    expect(screen.queryByText('Alınan ön ödeme')).not.toBeInTheDocument();
  });

  it('does not render Exely payment information on direct bookings', () => {
    render(<ExelyPrepaymentSummary booking={{ ...booking(), channel: 'direct' }} />);
    expect(screen.queryByTestId('exely-prepayment-summary')).not.toBeInTheDocument();
  });
});
