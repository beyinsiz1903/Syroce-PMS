import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { compileExelyGuestPrices, sameExelyGuestPrices } from '../exelyPlacements';
import { ExelyPlacementEditor } from '../ExelyPlacementEditor';
import { RateDeliveryCard } from '../RateDeliveryCard';
import { buildRateUpdateReview } from '../updateReview';
import { OccupancyPricingEditor } from '../BulkUpdatePanel';

const rule = { pricing_type: 'per_person', base_occupancy: 2, currency: 'USD', exely_placements_reviewed: true,
  exely_price_placements: [
    { kind: 'adult_main', number_of_guests: 1, price_mode: 'percentage', value: 90 },
    { kind: 'adult_main', number_of_guests: 3, price_mode: 'percentage', value: 125 },
    { kind: 'child_main', min_age: 3, max_age: 6, price_mode: 'fixed', value: 20 },
    { kind: 'adult_extra', price_mode: 'fixed', value: 30 },
    { kind: 'child_extra', min_age: 3, max_age: 6, price_mode: 'percentage', value: 10 },
    { kind: 'child_without_bed', min_age: 0, max_age: 2, price_mode: 'fixed', value: 0 },
  ] };

describe('Exely explicit placements in the existing editor', () => {
  it('compares receipt values rather than JSON key order, without accepting a missing placement', () => {
    const expected = compileExelyGuestPrices(rule, 100, 'USD');
    const reordered = expected.map(row => Object.fromEntries(Object.entries(row).reverse())).reverse();
    expect(sameExelyGuestPrices(expected, reordered)).toBe(true);
    expect(sameExelyGuestPrices(expected, reordered.slice(1))).toBe(false);
    expect(sameExelyGuestPrices(expected, undefined)).toBe(false);
  });
  it('matches backend totals and exclusive child age boundaries without a per-person multiplier', () => {
    const result = compileExelyGuestPrices(rule, 100, 'USD');
    expect(result).toEqual([
      { kind: 'adult_extra', amount: 30 },
      { kind: 'adult_main', amount: 90, number_of_guests: 1 },
      { kind: 'adult_main', amount: 100, number_of_guests: 2 },
      { kind: 'adult_main', amount: 125, number_of_guests: 3 },
      { kind: 'child_extra', amount: 10, min_age: 3, max_age: 7 },
      { kind: 'child_main', amount: 20, min_age: 3, max_age: 7 },
      { kind: 'child_without_bed', amount: 0, min_age: 0, max_age: 3 },
    ]);
    expect(compileExelyGuestPrices({ ...rule, pricing_type: 'per_room' }, 100, 'USD')).toEqual([{ kind: 'adult_main', number_of_guests: 2, amount: 100 }]);
  });

  it.each([
    { exely_placements_reviewed: false }, { currency: 'TRY' },
    { exely_price_placements: [{ kind: 'adult_main', number_of_guests: 2, price_mode: 'fixed', value: 100 }] },
    { exely_price_placements: [{ kind: 'child_main', min_age: 0, max_age: 18, price_mode: 'fixed', value: 0 }] },
    { exely_price_placements: [{ kind: 'adult_extra', price_mode: 'fixed', value: '' }] },
  ])('blocks malformed/unreviewed tariff %j', mutation => {
    expect(() => compileExelyGuestPrices({ ...rule, ...mutation }, 100, 'USD')).toThrow();
  });

  it('reviews all placements and includes them in quota costs before a write', () => {
    const result = buildRateUpdateReview({ dateFrom: '2030-01-01', dateTo: '2030-01-02', allDays: true,
      channelProvider: 'exely', selections: { STD: new Set(['BASE']) }, enabledFields: new Set(['rate']),
      roomValues: { STD: { rate: 100 } }, occupancyPricingRules: { STD: rule }, currency: 'USD' });
    expect(result.errors).toEqual([]);
    expect(result.priceSummaries[0].prices).toEqual(compileExelyGuestPrices(rule, 100, 'USD'));
    expect(result.warnings).toEqual([]);
    expect(result.notes).toEqual([]);
  });

  it('invalidates placement confirmation whenever a rate changes', () => {
    const Harness = () => {
      const [draft, setDraft] = useState(rule);
      return <ExelyPlacementEditor draft={draft} base={100} currency="USD" update={(field, value) => setDraft(prev => ({ ...prev, [field]: value }))} />;
    };
    render(<Harness />);
    expect(screen.getByTestId('exely-placements-reviewed')).toBeChecked();
    fireEvent.change(screen.getByLabelText('1. yerleşim fiyatı'), { target: { value: '85' } });
    expect(screen.getByTestId('exely-placements-reviewed')).not.toBeChecked();
    expect(screen.getByTestId('exely-placement-preview')).toHaveTextContent('1 yetişkin: 85 USD');
  });

  it('allows changing included adults and entering a separate single-adult price without saving/reloading first', () => {
    render(<OccupancyPricingEditor roomType={{ code: 'STD', name: 'Standart' }} open onToggle={vi.fn()} onSave={vi.fn()}
      rule={{ pricing_type: 'per_person', base_occupancy: 1 }} currentBaseRate={100} currency="USD" currencySymbol="$" channelProvider="exely" />);
    const adults = screen.getByText('Fiyata dahil yetişkin').parentElement.querySelector('input');
    fireEvent.change(adults, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Yetişkin fiyatı ekle' }));
    fireEvent.change(screen.getByLabelText('1. fiyat yöntemi'), { target: { value: 'fixed' } });
    fireEvent.change(screen.getByLabelText('1. yerleşim fiyatı'), { target: { value: '80' } });
    expect(screen.getByTestId('exely-placement-preview')).toHaveTextContent('1 yetişkin: 80 USD');
    expect(screen.getByTestId('exely-placement-preview')).toHaveTextContent('2 yetişkin: 100 USD');
    const review = screen.getByTestId('exely-placements-reviewed');
    expect(review).toBeEnabled();
    expect(review).not.toBeChecked();
    fireEvent.click(review);
    expect(review).toBeChecked();
    fireEvent.change(adults, { target: { value: '' } });
    expect(review).not.toBeChecked();
    expect(review).toBeDisabled();
    expect(screen.getByTestId('exely-placement-editor')).toHaveTextContent('Fiyata dahil yetişkin sayısını kaydedin.');
  });
});

describe('hotel-facing delivery card', () => {
  const receipt = { data: { saved: 2908, provider_verified: true, provider_delivery_state: 'CONFIRMED',
    price_guest_prices: { '5003299': compileExelyGuestPrices(rule, 100, 'USD') } }, dateFrom: '2026-11-06', dateTo: '2028-11-01',
    fields: ['rate'], roomCount: 2, currency: 'USD', roomNames: { '5003299': 'Standart' } };
  it('uses human labels, collapsed details and a dismiss action, not raw XML or room IDs', () => {
    const dismiss = vi.fn();
    render(<RateDeliveryCard receipt={receipt} feedback={{ level: 'success', message: 'Teslimat doğrulandı.' }} onDismiss={dismiss} />);
    const card = screen.getByTestId('rate-delivery-receipt');
    expect(card).toHaveTextContent('Teslim edildi');
    expect(card).toHaveTextContent('2.908 güncellendi');
    expect(card).not.toHaveTextContent(/NumberOfGuests|CONFIRMED|5003299/);
    expect(within(card).getByText('Standart').closest('details')).not.toHaveAttribute('open');
    fireEvent.click(screen.getByRole('button', { name: 'Son güncelleme kartını gizle' }));
    expect(dismiss).toHaveBeenCalledOnce();
  });
  it('never styles an unknown response as delivered', () => {
    render(<RateDeliveryCard receipt={{ ...receipt, data: { provider_delivery_state: 'UNKNOWN' } }} feedback={{ level: 'warning', message: 'Tekrar göndermeden önce uzlaştırın.' }} />);
    expect(screen.getByTestId('rate-delivery-receipt')).toHaveTextContent('Sonuç doğrulanamadı');
    expect(screen.getByTestId('rate-delivery-receipt')).not.toHaveTextContent('Teslim edildi');
  });
  it('keeps a partly delivered selection with a later unknown outcome visibly unconfirmed', () => {
    render(<RateDeliveryCard receipt={{ ...receipt, data: { provider_delivery_state: 'PARTIAL', outcome_unknown: true } }} feedback={{ level: 'warning', message: 'Tekrar göndermeden önce uzlaştırın.' }} />);
    expect(screen.getByTestId('rate-delivery-receipt')).toHaveTextContent('Sonuç doğrulanamadı');
    expect(screen.getByTestId('rate-delivery-receipt')).not.toHaveTextContent('Teslim edildi');
  });
});
