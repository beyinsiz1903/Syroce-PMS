import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosDelete, axiosGet, axiosPatch, axiosPost, confirmDialog } = vi.hoisted(() => ({
  axiosDelete: vi.fn(),
  axiosGet: vi.fn(),
  axiosPatch: vi.fn(),
  axiosPost: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    delete: axiosDelete,
    get: axiosGet,
    patch: axiosPatch,
    post: axiosPost,
  },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/components/TestBookingVerification', () => ({
  default: () => <div>test-booking-verification</div>,
}));

vi.mock('@/components/MaybeLayout', () => ({
  default: ({ children }) => <>{children}</>,
}));

import ChannelConnections from '@/pages/ChannelConnections';
import ExelyIntegration from '@/pages/ExelyIntegration';
import HotelRunnerIntegration from '@/pages/HotelRunnerIntegration';
import MappingManager from '@/pages/MappingManager';

const hotelRunnerResponse = (url) => {
  if (url.endsWith('/connection')) return { connected: true, connection: { property_name: 'Demo Hotel' } };
  if (url.endsWith('/live-activation/status')) return {
    ready_to_activate: true,
    mapping_ready: true,
    queued_write_count: 0,
    runtime: { ari_write_allowed: true },
    feature_flags: { write_enabled: false, shadow_mode: true },
    write_criteria: { met_count: 6, total_criteria: 6, criteria: [] },
  };
  if (url.endsWith('/callback-readiness')) return {
    ready: true,
    official_auth: 'token_plus_hr_id',
    callback_url: 'https://pms.syroce.com/api/channel-manager/hotelrunner/callback',
    credentials_configured: true,
    legacy_path_secret_configured: false,
    registration_requires_provider_confirmation: true,
    blockers: [],
  };
  if (url.endsWith('/room-mappings')) return {
    mappings: [{ id: 'hr-map-1', hr_inv_code: 'STD', hr_rate_code: 'BASE', pms_room_type: 'standard' }],
  };
  if (url.endsWith('/cached-rooms')) return {
    rooms: [{ inv_code: 'STD', rate_code: 'BASE', name: 'Standard', adult_capacity: 2, room_capacity: 2 }],
  };
  if (url.endsWith('/pms-room-types')) return { room_types: ['standard'] };
  return {};
};

const exelyResponse = (url) => {
  if (url.endsWith('/connection')) return {
    connected: true,
    connection: { property_name: 'Demo Hotel', currency: 'TRY' },
  };
  if (url.endsWith('/room-mappings')) return {
    mappings: [{
      id: 'exely-map-1',
      pms_room_type: 'standard',
      exely_room_code: 'STD',
      exely_rate_plan_code: 'BASE',
      exely_room_name: 'Standard',
    }],
  };
  return {};
};

describe('integration destructive action guards', () => {
  beforeEach(() => {
    axiosDelete.mockReset();
    axiosGet.mockReset();
    axiosPatch.mockReset();
    axiosPost.mockReset();
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(false);
    axiosGet.mockImplementation((url) => Promise.resolve({
      data:
        url.includes('/hotelrunner/') || url.includes('/hotelrunner-v2/')
          ? hotelRunnerResponse(url)
          : exelyResponse(url),
    }));
  });

  afterEach(() => cleanup());

  it('does not disconnect or delete mappings without HotelRunner confirmation', async () => {
    render(<HotelRunnerIntegration user={{}} tenant={{}} />);

    fireEvent.click(await screen.findByTestId('hr-disconnect-btn'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axiosDelete).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('tab-mappings'));
    fireEvent.click(await screen.findByTestId('delete-mapping-STD'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(2));
    expect(axiosDelete).not.toHaveBeenCalled();
  });

  it('shows the official HotelRunner callback contract without a secret action', async () => {
    render(<HotelRunnerIntegration user={{}} tenant={{}} />);

    expect(await screen.findByTestId('hr-callback-readiness-card')).toHaveTextContent('token + HR_ID');
    expect(screen.getByTestId('hr-callback-url')).toHaveValue(
      'https://pms.syroce.com/api/channel-manager/hotelrunner/callback',
    );
    expect(screen.queryByTestId('hr-webhook-secret-rotate-btn')).not.toBeInTheDocument();
    expect(screen.queryByText(/HotelRunner paneline.*secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/The Canyon/i)).not.toBeInTheDocument();
    expect(screen.getByText(/ilgili tesis için HotelRunner tarafında kayıtlı/i)).toBeInTheDocument();
  });

  it('does not enable HotelRunner live writes without explicit confirmation', async () => {
    render(<HotelRunnerIntegration user={{}} tenant={{}} />);

    fireEvent.click(await screen.findByTestId('hr-enable-live-write-btn'));

    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axiosPost).not.toHaveBeenCalledWith(
      expect.stringContaining('/live-activation/enable'),
      expect.anything(),
      expect.anything(),
    );
  });

  it('does not disconnect, change currency, or delete mappings without Exely confirmation', async () => {
    render(<ExelyIntegration user={{}} tenant={{}} />);

    fireEvent.click(await screen.findByTestId('exely-disconnect-btn'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axiosDelete).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId('exely-currency-change'), { target: { value: 'USD' } });
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(2));
    expect(axiosPatch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('exely-tab-mappings'));
    fireEvent.click(await screen.findByTestId('exely-delete-mapping-0'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(3));
    expect(axiosDelete).not.toHaveBeenCalled();
  });

  it('does not delete a generic channel mapping without confirmation', async () => {
    axiosGet.mockImplementation((url) => {
      if (url.endsWith('/connectors')) {
        return Promise.resolve({ data: { connectors: [{ id: 'connector-1', display_name: 'Demo', provider: 'hotelrunner' }] } });
      }
      if (url.includes('/readiness-report')) {
        return Promise.resolve({
          data: {
            readiness: { score: 100, ready: true },
            mappings_by_type: {
              room_type: [{
                id: 'generic-map-1',
                pms_entity_id: 'standard',
                external_entity_id: 'STD',
                validation_status: 'valid',
              }],
            },
            pms_entities: { room_types: [] },
            external_entities: { room_types: [] },
            supported_mapping_types: ['room_type'],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<MappingManager user={{}} tenant={{}} />);
    fireEvent.click(await screen.findByTestId('delete-mapping-generic-map-1'));

    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axiosDelete).not.toHaveBeenCalled();
  });

  it('does not disconnect from the shared connections screen without confirmation', async () => {
    axiosGet.mockResolvedValue({
      data: {
        providers: [{
          provider: 'hotelrunner',
          connected: true,
          property_name: 'Demo Hotel',
          room_mappings_count: 1,
        }],
        pms_room_types: [],
      },
    });

    render(<ChannelConnections user={{ token: 'test-token', role: 'super_admin' }} tenant={{}} />);
    fireEvent.click(await screen.findByTestId('hotelrunner-disconnect-btn'));

    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(axiosDelete).not.toHaveBeenCalled();
  });
});
