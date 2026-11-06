import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RatePublishReview } from '../RatePublishReview';
import { buildRateUpdateReview } from '../updateReview';

const input = {
  dateFrom: '2026-11-06', dateTo: '2028-11-01', allDays: true, channelProvider: 'exely', currency: 'USD',
  selections: { '5003299': new Set(['10003870', '10003869']), '5003300': new Set(['10003870', '10003869']) },
  roomTypes: [{ code: '5003299', name: 'Standart' }, { code: '5003300', name: 'Deluxe' }],
  ratePlans: [{ code: '10003870', name: 'Base rate USD' }, { code: '10003869', name: 'Non-ref rate USD' }],
  enabledFields: new Set(['rate']), roomValues: { '5003299': { rate: 100 }, '5003300': { rate: 120 } },
  occupancyPricingRules: { '5003299': { base_occupancy: 2 }, '5003300': { base_occupancy: 2 } },
};
const show = (overrides = {}, props = {}) => {
  const review = buildRateUpdateReview({ ...input, ...overrides });
  const onPublish = vi.fn(), onClose = vi.fn();
  render(<RatePublishReview review={review} onPublish={onPublish} onClose={onClose} {...props} />);
  return { review, onPublish, onClose, dialog: screen.getByRole('dialog', { name: 'Gönderim özeti' }) };
};

describe('hotel-facing publish summary', () => {
  it('turns the screenshot into two named prices, without technical warnings or a false zero-channel alarm', () => {
    const { review, dialog, onPublish, onClose } = show();
    expect(review).toMatchObject({ dateCount: 727, roomCount: 2, planCount: 4, cellCount: 2908, targetLabel: 'Exely' });
    expect(review.errors).toEqual([]);
    expect(review.warnings).toEqual([]);
    expect(within(dialog).getByText('6 Kas 2026 – 1 Kas 2028')).toBeInTheDocument();
    const standard = within(dialog).getByRole('region', { name: 'Standart fiyat özeti' });
    const deluxe = within(dialog).getByRole('region', { name: 'Deluxe fiyat özeti' });
    expect(standard).toHaveTextContent('2 yetişkin · oda/gece');
    expect(standard).toHaveTextContent('100 USD');
    expect(deluxe).toHaveTextContent('2 yetişkin · oda/gece');
    expect(deluxe).toHaveTextContent('120 USD');
    expect(standard).toHaveTextContent('Base rate USD · Non-ref rate USD');
    expect(within(dialog).getByText('Exely')).toBeInTheDocument();
    expect(dialog).toHaveTextContent('Diğer kişi, çocuk ve ek yatak tarifeleri bu işlemde güncellenmez.');
    expect(dialog).not.toHaveTextContent(/XML|NumberOfGuests|5003299|5003300|10003870|10003869|OTA|CONFIRMED/);
    expect(screen.queryByTestId('rate-review-warnings')).not.toBeInTheDocument();
    expect(onPublish).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    expect(onPublish).toHaveBeenCalledOnce();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Kapat' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('preserves every explicit adult, child, extra-bed and zero-price tariff with its correct unit and inclusive ages', () => {
    const { dialog, review } = show({ dateTo: '2026-11-07', selections: { '5003299': new Set(['10003870']) },
      occupancyPricingRules: { '5003299': { base_occupancy: 2, pricing_type: 'per_person', currency: 'USD', exely_placements_reviewed: true,
        exely_price_placements: [
          { kind: 'adult_main', number_of_guests: 1, price_mode: 'percentage', value: 90 },
          { kind: 'child_main', min_age: 3, max_age: 6, price_mode: 'fixed', value: 20 },
          { kind: 'adult_extra', price_mode: 'fixed', value: 30 },
          { kind: 'child_extra', min_age: 3, max_age: 6, price_mode: 'fixed', value: 10 },
          { kind: 'child_without_bed', min_age: 0, max_age: 2, price_mode: 'fixed', value: 0 },
        ] } } });
    expect(review.errors).toEqual([]);
    expect(review.priceSummaries[0].prices).toHaveLength(6);
    expect(dialog).toHaveTextContent('1 yetişkin · oda/gece');
    expect(dialog).toHaveTextContent('90 USD');
    expect(dialog).toHaveTextContent('Çocuk · ana yatak · 3–6 yaş · çocuk/gece');
    expect(dialog).toHaveTextContent('20 USD');
    expect(dialog).toHaveTextContent('Yetişkin · ek yatak · kişi/gece');
    expect(dialog).toHaveTextContent('30 USD');
    expect(dialog).toHaveTextContent('Çocuk · ek yatak · 3–6 yaş · çocuk/gece');
    expect(dialog).toHaveTextContent('Çocuk · yataksız · 0–2 yaş · çocuk/gece');
    expect(within(dialog).getByText('0 USD')).toBeInTheDocument();
    expect(dialog).not.toHaveTextContent('bu işlemde güncellenmez');
    expect(screen.queryByTestId('rate-review-warnings')).not.toBeInTheDocument();
  });

  it('keeps genuine sales-closure, automatic-reset and manual-inventory risks in the warning area', () => {
    const { review } = show({ dateTo: '2026-11-07', enabledFields: new Set(['availability', 'stop_sell', 'min_stay']),
      roomValues: { '5003299': { availability: 3, stop_sell: true, min_stay: 0 }, '5003300': { availability: '', stop_sell: false, min_stay: 0 } } });
    const warnings = screen.getByTestId('rate-review-warnings');
    expect(review.errors).toEqual([]);
    expect(warnings).toHaveTextContent('Standart: Elle girdiğiniz 3 oda satışa sunulacak');
    expect(warnings).toHaveTextContent('fazla rezervasyona yol açabilir');
    expect(warnings).toHaveTextContent('Standart satışa kapatılacak');
    expect(warnings).toHaveTextContent('Minimum konaklama kısıtı kaldırılacak');
    expect(warnings).toHaveTextContent('Deluxe: Müsaitlik otomatik hesaba dönecek');
  });

  it.each([
    { occupancyPricingRules: {} },
    { occupancyPricingRules: { '5003299': { base_occupancy: 2, pricing_type: 'per_person', provider_pricing_verified: false },
      '5003300': { base_occupancy: 2 } } },
    { roomValues: { '5003299': { rate: 0 }, '5003300': { rate: 120 } } },
    { ratePlans: [{ code: '10003870', price_upload_is_allowed: false }] },
    { dateTo: '2028-11-10', enabledFields: new Set(['availability']), roomValues: { '5003299': { availability: 3 }, '5003300': { availability: 3 } } },
    { occupancyPricingRules: { '5003299': { base_occupancy: 2, pricing_type: 'per_person', currency: 'USD',
      exely_price_placements: [{ kind: 'adult_main', number_of_guests: 1, price_mode: 'fixed', value: 90 }] } } },
  ])('still blocks publication when a safety preflight fails: %j', overrides => {
    const { review, onPublish } = show(overrides);
    expect(review.errors.length).toBeGreaterThan(0);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByTestId('rate-confirm-publish')).toBeDisabled();
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    expect(onPublish).not.toHaveBeenCalled();
  });

  it('keeps save-in-progress disabled and never renders unmapped room identifiers as display names', () => {
    const { dialog, onPublish } = show({ roomTypes: [], ratePlans: [] }, { saving: true });
    expect(dialog).toHaveTextContent('Oda tipi 1');
    expect(dialog).toHaveTextContent('Oda tipi 2');
    expect(dialog).not.toHaveTextContent(/5003299|5003300|10003870/);
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    expect(onPublish).not.toHaveBeenCalled();
  });

  it('shows the screenshot missing-person-rule approval before publish, with the room name and a clear next step', () => {
    const { dialog, onPublish } = show({ occupancyPricingRules: Object.fromEntries(input.roomTypes.map(room => [room.code,
      { base_occupancy: 2, pricing_type: 'per_person', provider_pricing_verified: false }])) });
    expect(screen.getByRole('alert')).toHaveTextContent('Standart: Kişi bazlı fiyatlar kontrol edilmemiş.');
    expect(screen.getByRole('alert')).toHaveTextContent('Deluxe: Kişi bazlı fiyatlar kontrol edilmemiş.');
    expect(screen.getByRole('alert')).toHaveTextContent('“Kuralı düzenle” bölümünde Exely ile eşleşmesini kontrol edip kaydedin.');
    expect(dialog).not.toHaveTextContent(/5003299|5003300/);
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    expect(onPublish).not.toHaveBeenCalled();
  });

  it('retains the existing explicitly approved base-only person-pricing path without silently approving a missing review', () => {
    const { review } = show({ occupancyPricingRules: Object.fromEntries(input.roomTypes.map(room => [room.code,
      { base_occupancy: 2, pricing_type: 'per_person', provider_pricing_verified: true }])) });
    expect(review.errors).toEqual([]);
    expect(screen.getByTestId('rate-confirm-publish')).toBeEnabled();
    expect(review.priceSummaries.every(room => room.prices.length === 1)).toBe(true);
  });

  it('describes an agency-only target without claiming an Exely delivery or imposing its adult-placement requirement', () => {
    const { dialog, review } = show({ agenciesOnly: true, occupancyPricingRules: {} });
    expect(review.errors).toEqual([]);
    expect(review.targetLabel).toBe('Seçili acenteler');
    expect(dialog).toHaveTextContent('Otel takvimi ve satış kanalları değişmez');
    expect(dialog).not.toHaveTextContent('Exely');
    expect(screen.queryByTestId('rate-review-warnings')).not.toBeInTheDocument();
  });
});
