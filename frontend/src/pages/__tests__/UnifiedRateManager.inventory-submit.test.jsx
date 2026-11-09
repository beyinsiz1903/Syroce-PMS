import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import UnifiedRateManager from '@/pages/UnifiedRateManager';

const { confirmDialog } = vi.hoisted(() => ({ confirmDialog: vi.fn() }));
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog }));
vi.mock('@/components/MaybeLayout', () => ({ default: ({ children }) => children }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

describe('actual rate editor inventory submission', () => {
  afterEach(() => vi.restoreAllMocks());
  beforeEach(() => {
    vi.clearAllMocks();
    confirmDialog.mockResolvedValue(true);
    axios.get.mockImplementation(async url => {
      if (url.endsWith('/detect-provider')) return { data: { provider: 'exely' } };
      if (url.includes('/grid?')) return { data: {
        room_types: [{ code: 'STD', name: 'Standart' }],
        rate_plans: [{ code: 'BASE', name: 'Base' }], grid: [], currency: 'USD',
      } };
      if (url.endsWith('/push-providers')) return { data: { providers: [{ name: 'Exely', mode: 'live' }] } };
      if (url.endsWith('/agencies')) return { data: { agencies: [] } };
      if (url.endsWith('/circuit-breakers')) return { data: { breakers: [] } };
      throw new Error('Unexpected unmocked GET: ' + url);
    });
    axios.post.mockResolvedValue({ data: { saved: 1, provider: 'exely', provider_verified: true,
      provider_delivery_state: 'CONFIRMED', availability_input_mode: 'remaining' } });
  });

  it.each([['', null], ['0', 0], ['3', 3], ['1e2', 100]])(
    'submits input %s as %s through the existing button and endpoint', async (input, expected) => {
      render(<MemoryRouter><UnifiedRateManager embedded /></MemoryRouter>);
      fireEvent.click(await screen.findByTestId('room-type-check-STD', {}, { timeout: 5000 }));
      fireEvent.click(screen.getByTestId('field-availability'));
      const field = screen.getByTestId('avail-input-STD');
      if (input !== '') fireEvent.change(field, { target: { value: input } });
      fireEvent.click(screen.getByTestId('bulk-update-btn'));
      expect(screen.queryByText('Yayınlamadan önce düzeltin')).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId('rate-confirm-publish'));
      await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
      expect(axios.post).toHaveBeenCalledWith(
        '/channel-manager/unified-rate-manager/bulk-remaining-update',
        expect.objectContaining({
          update_fields: ['availability'],
          per_room_values: [expect.objectContaining({
            room_type_code: 'STD', rate_plan_codes: ['BASE'], availability: expected,
          })],
        }),
        expect.anything(),
      );
      expect(confirmDialog).toHaveBeenCalledTimes(1);
      expect(toast.error).not.toHaveBeenCalled();
      expect(await screen.findByTestId('rate-delivery-receipt')).toHaveTextContent('Teslim edildi');
    },
  );

  it('does not submit a blank automatic reset if the normal confirmation is declined', async () => {
    confirmDialog.mockResolvedValue(false);
    render(<MemoryRouter><UnifiedRateManager embedded /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('room-type-check-STD'));
    fireEvent.click(screen.getByTestId('field-availability'));
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axios.post).not.toHaveBeenCalled();
  });

  it.each([true, false])('sends the reviewed adult occupancy and shows delivery or no change (delivered=%s)', async delivered => {
    const implementation = axios.get.getMockImplementation();
    axios.get.mockImplementation(async (url, ...args) => {
      const result = await implementation(url, ...args);
      if (url.includes('/grid?')) result.data.occupancy_pricing_rules = { STD: { base_occupancy: 3, base_occupancy_explicit: true } };
      return result;
    });
    axios.post.mockResolvedValue({ data: { saved: 1, provider: 'exely', provider_verified: delivered,
      provider_delivery_state: delivered ? 'CONFIRMED' : 'UNCHANGED', price_occupancies: { STD: 3 } } });
    render(<MemoryRouter><UnifiedRateManager embedded /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('room-type-check-STD'));
    fireEvent.click(screen.getByTestId('field-rate'));
    fireEvent.change(screen.getByTestId('rate-input-STD'), { target: { value: '100' } });
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    const priceRow = within(screen.getByTestId('rate-publish-review')).getByText('3 yetişkin · oda/gece').closest('li');
    expect(priceRow).toHaveTextContent('100 USD');
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0][1].per_room_values[0]).toMatchObject({ rate: 100, rate_number_of_guests: 3 });
    const receipt = await screen.findByTestId('rate-delivery-receipt');
    expect(receipt).toHaveTextContent('3 yetişkin · ana yatak');
    expect(receipt).toHaveTextContent(delivered ? 'Teslim edildi' : 'Fiyatlar güncel');
    if (!delivered) expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('Yeni gönderim gerekmedi'), expect.anything());
  });

  it('submits two room types and 731 nights in one existing UI request, preserving manual versus automatic stock', async () => {
    const warnings = vi.spyOn(console, 'warn');
    const errors = vi.spyOn(console, 'error');
    const implementation = axios.get.getMockImplementation();
    axios.get.mockImplementation(async (url, ...args) => url.includes('/grid?') ? { data: {
      room_types: [{ code: 'STD', name: 'Standart' }, { code: 'DLX', name: 'Deluxe' }],
      rate_plans: [{ code: 'BASE', name: 'Base' }], grid: [], currency: 'USD',
    } } : implementation(url, ...args));
    render(<MemoryRouter><UnifiedRateManager embedded /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('room-type-check-STD'));
    fireEvent.click(screen.getByTestId('room-type-check-DLX'));
    fireEvent.click(screen.getByTestId('field-availability'));
    fireEvent.change(screen.getByTestId('bulk-date-from'), { target: { value: '2026-11-05' } });
    fireEvent.change(screen.getByTestId('bulk-date-to'), { target: { value: '2028-11-04' } });
    fireEvent.change(screen.getByTestId('avail-input-STD'), { target: { value: '3' } });
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    expect(screen.queryByText('Yayınlamadan önce düzeltin')).not.toBeInTheDocument();
    expect(screen.getByTestId('bulk-summary')).toHaveTextContent('731 hedef gece');
    expect(screen.getByTestId('bulk-summary')).toHaveTextContent('1.462 fiyat-plan hücresi');
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post).toHaveBeenCalledWith('/channel-manager/unified-rate-manager/bulk-remaining-update',
      expect.objectContaining({ start_date: '2026-11-05', end_date: '2028-11-04',
        update_fields: ['availability'], per_room_values: [
          expect.objectContaining({ room_type_code: 'STD', rate_plan_codes: ['BASE'], availability: 3 }),
          expect.objectContaining({ room_type_code: 'DLX', rate_plan_codes: ['BASE'], availability: null }),
        ] }), expect.anything());
    expect(await screen.findByTestId('rate-delivery-receipt')).toHaveTextContent('Teslim edildi');
    expect([...warnings.mock.calls, ...errors.mock.calls].flat().join(' ')).not.toMatch(/uncontrolled|controlled value/);
  });

  it.each([true, false])('sends reviewed placements and checks the complete receipt (new server=%s)', async newServer => {
    const expectedPrices = [
      { kind: 'adult_main', number_of_guests: 1, amount: 90 },
      { kind: 'adult_main', number_of_guests: 2, amount: 100 },
      { kind: 'child_extra', min_age: 3, max_age: 7, amount: 10 },
    ];
    if (newServer) axios.post.mockResolvedValue({ data: { saved: 1, provider_verified: true, provider_delivery_state: 'CONFIRMED', price_guest_prices: { STD: expectedPrices } } });
    const implementation = axios.get.getMockImplementation();
    axios.get.mockImplementation(async (url, ...args) => {
      const result = await implementation(url, ...args);
      if (url.includes('/grid?')) {
        result.data.exely_placement_tariffs_version = 1;
        result.data.pricing_settings = { STD: 'per_person' };
        result.data.occupancy_pricing_rules = { STD: { pricing_type: 'per_person', base_occupancy: 2, currency: 'USD',
          exely_placements_reviewed: true, exely_price_placements: [
            { kind: 'adult_main', number_of_guests: 1, price_mode: 'percentage', value: 90 },
            { kind: 'child_extra', min_age: 3, max_age: 6, price_mode: 'fixed', value: 10 },
          ] } };
      }
      return result;
    });
    render(<MemoryRouter><UnifiedRateManager embedded /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('room-type-check-STD'));
    fireEvent.click(screen.getByTestId('field-rate'));
    fireEvent.change(screen.getByTestId('rate-input-STD'), { target: { value: '100' } });
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    const review = screen.getByTestId('rate-publish-review');
    expect(within(review).getByText('1 yetişkin · oda/gece').closest('li')).toHaveTextContent('90 USD');
    expect(within(review).getByText('Çocuk · ek yatak · 3–6 yaş · çocuk/gece').closest('li')).toHaveTextContent('10 USD');
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0][0]).toBe('/channel-manager/unified-rate-manager/bulk-grid-update');
    expect(axios.post.mock.calls[0][1].per_room_values[0].rate_guest_prices).toEqual(expectedPrices);
    expect(await screen.findByTestId('rate-delivery-receipt')).toHaveTextContent(newServer ? 'Teslim edildi' : 'Sonuç doğrulanamadı');
  });
});
