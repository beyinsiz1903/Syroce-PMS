import { beforeEach, describe, expect, it, vi } from 'vitest';
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
});
