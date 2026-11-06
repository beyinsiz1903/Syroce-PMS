import { useState } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OccupancyPricingEditor } from '../OccupancyPricingEditor';
import { ExelyPlacementEditor } from '../ExelyPlacementEditor';
import { compileExelyGuestPrices } from '../exelyPlacements';
import { nextAdultPlacement, nextChildAgeBand, validateGuestPricingDraft } from '../guestPricingEditor';

const pmsBands = [
  { min_age: 0, max_age: 6, pricing_mode: 'free', value: 0 },
  { min_age: 7, max_age: 11, pricing_mode: 'adult_percentage', value: 50 },
  { min_age: 12, max_age: 17, pricing_mode: 'adult_rate', value: 0 },
];
const rule = { pricing_type: 'per_person', base_occupancy: 2, extra_adult_rate: 20,
  extra_adult_rate_type: 'fixed', child_age_bands: pmsBands, currency: 'USD', max_occupancy: null,
  exely_price_placements: [{ kind: 'adult_main', number_of_guests: 1, price_mode: 'fixed', value: 80 }],
  exely_placements_reviewed: true };
const editor = (props = {}) => render(<OccupancyPricingEditor roomType={{ code: 'STD', name: 'Standart' }} open
  onToggle={vi.fn()} onSave={vi.fn()} rule={rule} currentBaseRate={100} currency="USD" currencySymbol="$" channelProvider="exely" {...props} />);
const placementEditor = (overrides = {}, base = 100, pricingType) => {
  const Harness = () => {
    const [draft, setDraft] = useState({ ...rule, ...overrides });
    return <><ExelyPlacementEditor draft={draft} base={base} currency="USD" pricingType={pricingType}
      update={(field, value) => setDraft(prev => ({ ...prev, [field]: value }))} />
      <output data-testid="draft">{JSON.stringify(draft)}</output></>;
  };
  render(<Harness />);
};

describe('separate local and channel pricing in the existing rule editor', () => {
  it('opens the channel table first and exposes the distinct PMS calculation only in its own tab', () => {
    editor();
    expect(screen.getByRole('tab', { name: 'Exely tarifeleri' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Exely tarifeleri' })).toHaveTextContent('1 yetişkin: 80 USD');
    expect(screen.queryByRole('spinbutton', { name: 'PMS ek yetişkin ücreti' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'PMS ek ücretleri' }));
    const pms = screen.getByRole('tabpanel', { name: 'PMS ek ücretleri' });
    expect(pms).toHaveTextContent('Taban oda fiyatının yüzdesi değildir.');
    expect(pms).toHaveTextContent('20 USD × %50 = 10 USD');
    expect(pms).toHaveTextContent('2 yetişkin + 7–11 yaş 1 çocuk110 USD+10 USD çocuk farkı');
    expect(pms).toHaveTextContent('Bu ücretler Exely’ye otomatik kopyalanmaz');
  });

  it('keeps entered values while switching tabs and supports keyboard tab navigation', () => {
    editor();
    fireEvent.change(screen.getByLabelText('1. yerleşim fiyatı'), { target: { value: '85' } });
    const exely = screen.getByRole('tab', { name: 'Exely tarifeleri' });
    fireEvent.keyDown(exely, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'PMS ek ücretleri' })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole('tab', { name: 'PMS ek ücretleri' }), { key: 'Home' });
    expect(exely).toHaveFocus();
    expect(screen.getByLabelText('1. yerleşim fiyatı')).toHaveValue(85);
    expect(screen.getByTestId('exely-placements-reviewed')).not.toBeChecked();
  });

  it('keeps PMS supplements and Exely tariffs independent and saves only rule data', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    editor({ onSave: save });
    fireEvent.click(screen.getByRole('tab', { name: 'PMS ek ücretleri' }));
    fireEvent.change(screen.getByLabelText('PMS ek yetişkin ücreti'), { target: { value: '30' } });
    fireEvent.click(screen.getByTestId('save-occupancy-rule-STD'));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ extra_adult_rate: 30, child_age_bands: pmsBands,
      exely_price_placements: rule.exely_price_placements, exely_placements_reviewed: true }));
    expect(save.mock.calls[0][0]).not.toHaveProperty('date_from');
    expect(save.mock.calls[0][0]).not.toHaveProperty('rate');
  });

  it('never saves a blank child amount as zero, or previews it as a free child', () => {
    const save = vi.fn(); editor({ onSave: save });
    fireEvent.click(screen.getByRole('tab', { name: 'PMS ek ücretleri' }));
    const band = screen.getByTestId('pms-child-band-1');
    fireEvent.change(within(band).getByLabelText('Ek yetişkin ücretinin %’si'), { target: { value: '' } });
    expect(screen.getByTestId('save-occupancy-rule-STD')).toBeDisabled();
    expect(screen.queryByTestId('occupancy-preview-STD')).not.toBeInTheDocument();
    expect(screen.getByTestId('guest-pricing-save-errors')).toHaveTextContent('ücretler geçerli olmalıdır');
    fireEvent.click(screen.getByTestId('save-occupancy-rule-STD'));
    expect(save).not.toHaveBeenCalled();
  });

  it('blocks blank child ages and overlapping ages; new bands fill an uncovered interval without assigning a free price', () => {
    editor(); fireEvent.click(screen.getByRole('tab', { name: 'PMS ek ücretleri' }));
    expect(screen.getByRole('button', { name: 'Kademe ekle' })).toBeDisabled();
    const first = screen.getByTestId('pms-child-band-0');
    fireEvent.change(within(first).getByLabelText('Bitiş yaşı'), { target: { value: '7' } });
    expect(screen.getByTestId('save-occupancy-rule-STD')).toBeDisabled();
    fireEvent.change(within(first).getByLabelText('Başlangıç yaşı'), { target: { value: '' } });
    expect(screen.getByTestId('save-occupancy-rule-STD')).toBeDisabled();
    fireEvent.change(within(first).getByLabelText('Başlangıç yaşı'), { target: { value: '0' } });
    fireEvent.change(within(first).getByLabelText('Bitiş yaşı'), { target: { value: '6' } });
    fireEvent.click(screen.getByRole('button', { name: '2. çocuk yaş kademesini sil' }));
    fireEvent.click(screen.getByRole('button', { name: 'Kademe ekle' }));
    const added = screen.getByTestId('pms-child-band-2');
    expect(within(added).getByLabelText('Başlangıç yaşı')).toHaveValue(7);
    expect(within(added).getByLabelText('Bitiş yaşı')).toHaveValue(11);
    expect(within(added).getByLabelText('Çocuk başı / gece (USD)')).toHaveValue(null);
    expect(screen.getByTestId('save-occupancy-rule-STD')).toBeDisabled();
  });

  it('does not show an over-capacity child as free', () => {
    editor({ rule: { ...rule, max_occupancy: 2 } });
    fireEvent.click(screen.getByRole('tab', { name: 'PMS ek ücretleri' }));
    expect(screen.getByTestId('occupancy-preview-STD')).toHaveTextContent('Kapasite aşılıyor');
    expect(screen.getByTestId('occupancy-preview-STD')).not.toHaveTextContent('Ücretsiz / dahil');
  });

  it('warns about a changed currency even if only Exely tariffs have fixed prices', () => {
    editor({ rule: { ...rule, extra_adult_rate: 0, child_age_bands: [{ min_age: 0, max_age: 17, pricing_mode: 'free', value: 0 }] }, currency: 'TRY' });
    expect(screen.getByTestId('occupancy-currency-warning-STD')).toHaveTextContent('USD girilmiş');
    expect(screen.getByTestId('exely-placements-reviewed')).not.toBeChecked();
  });
});

describe('guided Exely child and extra-bed tariffs', () => {
  it('adds a distinct adult occupancy instead of duplicating the base or a saved occupancy', () => {
    placementEditor(); fireEvent.click(screen.getByRole('button', { name: 'Yetişkin fiyatı ekle' }));
    expect(screen.getByLabelText('2. yetişkin sayısı')).toHaveValue(3);
    expect(screen.getByLabelText('2. yerleşim fiyatı')).toHaveValue(null);
    expect(screen.getByTestId('exely-placements-reviewed')).toBeDisabled();
  });

  it('gives an explicit free child choice, preserves inclusive ages, and never silently chooses the PMS child policy', () => {
    placementEditor({ exely_price_placements: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Çocuk fiyatı ekle' }));
    expect(screen.getByLabelText('1. ilk yaş')).toHaveValue(0);
    expect(screen.getByLabelText('1. son yaş')).toHaveValue(17);
    expect(screen.getByLabelText('1. yerleşim fiyatı')).toHaveValue(null);
    fireEvent.change(screen.getByLabelText('1. ilk yaş'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('1. son yaş'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('1. fiyat yöntemi'), { target: { value: 'free' } });
    expect(screen.getByTestId('exely-placement-amount-0')).toHaveTextContent('0 USD / çocuk başı / gece');
    const saved = JSON.parse(screen.getByTestId('draft').textContent);
    expect(saved.exely_price_placements).toEqual([{ kind: 'child_main', min_age: 3, max_age: 6, price_mode: 'fixed', value: 0 }]);
    expect(compileExelyGuestPrices({ ...saved, exely_placements_reviewed: true }, 100, 'USD')).toContainEqual({ kind: 'child_main', min_age: 3, max_age: 7, amount: 0 });
    expect(screen.getByTestId('exely-placements-reviewed')).not.toBeChecked();
  });

  it('shows per-child percentage amounts and bed types without multiplying by base adult count', () => {
    placementEditor({ exely_price_placements: [{ kind: 'child_extra', min_age: 7, max_age: 11, price_mode: 'percentage', value: 50 }] }, 120);
    expect(screen.getByTestId('exely-placement-amount-0')).toHaveTextContent('Taban oda fiyatı × %50');
    expect(screen.getByTestId('exely-placement-amount-0')).toHaveTextContent('60 USD / çocuk başı / gece');
    expect(screen.getByTestId('exely-placement-preview')).toHaveTextContent('7–11 yaş çocuk · ek yatak: 60 USD');
  });

  it('can prepare a valid percentage rule without inventing an amount when a base price has not been entered', () => {
    placementEditor({ exely_price_placements: [{ kind: 'child_extra', min_age: 7, max_age: 11, price_mode: 'percentage', value: 50 }] }, 0);
    expect(screen.queryByTestId('exely-placement-preview')).not.toBeInTheDocument();
    expect(screen.getByTestId('exely-placements-reviewed')).toBeEnabled();
    expect(screen.getByText(/Oda fiyatını girdiğinizde/)).toBeInTheDocument();
    expect(screen.getByTestId('exely-placement-amount-0')).not.toHaveTextContent('0 USD');
  });

  it('supports extra adults, without-bed children, and never presents room-based mode as sending extras', () => {
    placementEditor({ exely_price_placements: [] }, 100, 'per_room');
    expect(within(screen.getByTestId('exely-placement-editor')).getByRole('status')).toHaveTextContent('yalnız aşağıdaki taban oda fiyatı gönderilir');
    fireEvent.click(screen.getByRole('button', { name: 'Ek yatak fiyatı ekle' }));
    fireEvent.change(screen.getByLabelText('1. yerleşim fiyatı'), { target: { value: '30' } });
    expect(screen.getByTestId('exely-placement-preview')).toHaveTextContent('Yetişkin · ek yatak: 30 USD');
    expect(screen.getByRole('button', { name: 'Ek yatak fiyatı ekle' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('1. Exely yerleşim türü'), { target: { value: 'child_without_bed' } });
    expect(screen.getByLabelText('1. yerleşim fiyatı')).toHaveValue(null);
    expect(screen.getByTestId('exely-placements-reviewed')).not.toBeChecked();
  });

  it('requires a fresh comparison when a child age changes and blocks overlaps only for the same bed type', () => {
    placementEditor({ exely_price_placements: [
      { kind: 'child_main', min_age: 0, max_age: 6, price_mode: 'fixed', value: 10 },
      { kind: 'child_extra', min_age: 0, max_age: 6, price_mode: 'fixed', value: 15 },
    ] });
    expect(screen.getByTestId('exely-placements-reviewed')).toBeChecked();
    fireEvent.change(screen.getByLabelText('1. son yaş'), { target: { value: '7' } });
    expect(screen.getByTestId('exely-placements-reviewed')).not.toBeChecked();
    fireEvent.change(screen.getByLabelText('2. Exely yerleşim türü'), { target: { value: 'child_main' } });
    fireEvent.change(screen.getByLabelText('2. ilk yaş'), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText('2. son yaş'), { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('2. yerleşim fiyatı'), { target: { value: '10' } });
    expect(screen.getByTestId('exely-placements-reviewed')).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('çakışamaz');
  });
});

describe('draft validation and non-overlapping suggestions', () => {
  it.each(['', ' ', null, true, -1, Number.NaN, Number.POSITIVE_INFINITY])('rejects invalid or missing adult supplement %s', value => {
    expect(validateGuestPricingDraft({ ...rule, extra_adult_rate: value }).join(' ')).toContain('Ek yetişkin ücretini');
  });
  it('accepts explicit zero and rejects capacity below included adults', () => {
    expect(validateGuestPricingDraft({ ...rule, extra_adult_rate: 0 })).toEqual([]);
    expect(validateGuestPricingDraft({ ...rule, max_occupancy: 1 }).join(' ')).toContain('Maksimum kişi');
    expect(nextAdultPlacement([], 1)).toBe(2);
    expect(nextChildAgeBand(pmsBands)).toBeNull();
    expect(nextChildAgeBand([{ min_age: 3, max_age: 6 }])).toEqual({ min_age: 0, max_age: 2 });
  });
});
