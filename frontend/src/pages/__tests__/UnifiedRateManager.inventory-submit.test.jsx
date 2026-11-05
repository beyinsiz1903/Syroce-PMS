import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import UnifiedRateManager from '@/pages/UnifiedRateManager';

const { confirmDialog } = vi.hoisted(() => ({ confirmDialog: vi.fn() }));
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog }));
vi.mock('@/components/MaybeLayout', () => ({ default: ({ children }) => children }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

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
      fireEvent.click(await screen.findByTestId('room-type-check-STD'));
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
      expect(await screen.findByTestId('rate-delivery-receipt')).toHaveTextContent('CONFIRMED');
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

  it('sends the saved and reviewed adult occupancy with the price through the real editor', async () => {
    const implementation = axios.get.getMockImplementation();
    axios.get.mockImplementation(async (url, ...args) => {
      const result = await implementation(url, ...args);
      if (url.includes('/grid?')) result.data.occupancy_pricing_rules = { STD: { base_occupancy: 3, base_occupancy_explicit: true } };
      return result;
    });
    axios.post.mockResolvedValue({ data: { saved: 1, provider: 'exely', provider_verified: true,
      provider_delivery_state: 'CONFIRMED', price_occupancies: { STD: 3 } } });
    render(<MemoryRouter><UnifiedRateManager embedded /></MemoryRouter>);
    fireEvent.click(await screen.findByTestId('room-type-check-STD'));
    fireEvent.click(screen.getByTestId('field-rate'));
    fireEvent.change(screen.getByTestId('rate-input-STD'), { target: { value: '100' } });
    fireEvent.click(screen.getByTestId('bulk-update-btn'));
    expect(screen.getByTestId('rate-publish-review')).toHaveTextContent('100 — 3 yetişkin için oda/gece toplam fiyatı');
    fireEvent.click(screen.getByTestId('rate-confirm-publish'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0][1].per_room_values[0]).toMatchObject({ rate: 100, rate_number_of_guests: 3 });
    expect(await screen.findByTestId('rate-delivery-receipt')).toHaveTextContent('NumberOfGuests=3');
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
    expect(await screen.findByTestId('rate-delivery-receipt')).toHaveTextContent('CONFIRMED');
    expect([...warnings.mock.calls, ...errors.mock.calls].flat().join(' ')).not.toMatch(/uncontrolled|controlled value/);
  });
});
