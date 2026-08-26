import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EarlyLateChargeModal from '@/components/EarlyLateChargeModal';
import IdPhotoViewerButton from '@/components/IdPhotoViewerButton';
import { GuestsTab } from '@/pages/reservation-detail/InfoTabs';
import { VCCTab } from '@/pages/reservation-detail/VCCTab';

const { axiosGet, axiosPost } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  axiosPost: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    get: axiosGet,
    post: axiosPost,
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/api/axios', () => ({
  default: { post: axiosPost },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key.split('.').at(-1),
  }),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

function expectNestedLayer(content) {
  expect(content).toHaveClass('z-[80]');
  expect(
    Array.from(document.body.querySelectorAll('*')).some((element) =>
      element.classList.contains('z-[70]'),
    ),
  ).toBe(true);
}

describe('reservation detail nested overlays', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPost.mockReset();
    HTMLElement.prototype.hasPointerCapture = vi.fn(() => false);
    HTMLElement.prototype.setPointerCapture = vi.fn();
    HTMLElement.prototype.releasePointerCapture = vi.fn();
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => cleanup());

  it('opens the ID photo reason dialog above the reservation modal', () => {
    render(
      <div className="fixed inset-0 z-[60]">
        <IdPhotoViewerButton
          bookingId="booking-a"
          guestName="Test Misafir"
          user={{ role: 'admin' }}
          onlineCheckinCompleted
          idPhotoUploaded
        />
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Kimlik fotoğrafını görüntüle/i }));

    expectNestedLayer(screen.getByTestId('dialog-id-photo-reason'));
  });

  it('opens early/late charge calculation above the reservation modal', () => {
    render(
      <div className="fixed inset-0 z-[60]">
        <EarlyLateChargeModal
          open
          onClose={() => {}}
          bookingId="booking-a"
          direction="early_checkin"
        />
      </div>,
    );

    const dialog = screen.getByText('Erken Giriş Ek Ücreti').closest('[role="dialog"]');
    expectNestedLayer(dialog);
  });

  it('keeps VCC reveal confirmation and revealed card above the reservation modal', async () => {
    axiosGet.mockResolvedValue({
      data: {
        has_vcc: true,
        vcc: {
          view_count: 0,
          max_views: 3,
          locked: false,
          card_mask: '411111******1111',
        },
      },
    });
    axiosPost.mockResolvedValue({
      data: {
        card: {
          card_holder: 'TEST GUEST',
          card_number: '4111111111111111',
          expiry: '12/30',
          cvv: '123',
        },
        view_count: 1,
        remaining_views: 2,
        locked: false,
      },
    });

    render(
      <div className="fixed inset-0 z-[60]">
        <VCCTab booking={{ id: 'booking-a' }} />
      </div>,
    );

    const revealButton = await screen.findByRole('button', { name: /karti_goruntule/i });
    fireEvent.click(revealButton);
    expectNestedLayer(screen.getByRole('alertdialog'));

    fireEvent.click(screen.getByRole('button', { name: /evet_goster/i }));
    const cardDialog = await screen.findByText('Kart Bilgileri');
    expectNestedLayer(cardDialog.closest('[role="dialog"]'));
  });

  it('renders guest edit select menus above the reservation modal', async () => {
    render(
      <div className="fixed inset-0 z-[60]">
        <GuestsTab
          guests={[{ id: 'guest-a', name: 'Test Misafir', id_type: 'tc_kimlik' }]}
          booking={{ id: 'booking-a' }}
        />
      </div>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Düzenle/i }));
    const [idTypeSelect] = screen.getAllByRole('combobox');
    idTypeSelect.focus();
    fireEvent.keyDown(idTypeSelect, { key: 'ArrowDown' });

    await waitFor(() => expect(screen.getByRole('listbox')).toHaveClass('z-[70]'));
  });
});
