import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import GuestsTab from '@/components/pms/GuestsTab';
import GuestCreateDialog from '@/components/pms/GuestCreateDialog';
import { Tabs } from '@/components/ui/tabs';
import { toast } from 'sonner';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub);

const { post, patch, confirmDialog } = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('axios', () => ({ default: { post, patch } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/components/pms/IDScanner', () => ({ default: () => null }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => {
      const labels = {
        'pmsComponents.guests.mergeGuests': 'Misafir Birleştir',
        'pmsComponents.guests.mergeTitle': 'Misafirleri Birleştir',
        'pmsComponents.guests.merge': 'Birleştir',
        'pmsComponents.guests.preferencesBtn': 'Tercihler',
        'pmsComponents.guests.preferences': 'Tercihler',
        'pmsComponents.guests.save': 'Kaydet',
        'pmsComponents.guests.newBookingFor': 'Yeni Rezervasyon',
      };
      return labels[key] || fallback || key;
    },
  }),
}));

const guests = [
  { id: 'guest-primary', name: 'TST Primary', preferences: {} },
  { id: 'guest-duplicate', name: 'TST Duplicate', preferences: {} },
];

function renderGuests(props = {}) {
  const defaults = {
    guests,
    setOpenDialog: vi.fn(),
    setSelectedGuest360: vi.fn(),
    loadGuest360: vi.fn(),
    setNewBooking: vi.fn(),
    onGuestsChanged: vi.fn(),
  };
  const merged = { ...defaults, ...props };
  render(
    <MemoryRouter>
      <Tabs defaultValue="guests">
        <GuestsTab {...merged} />
      </Tabs>
    </MemoryRouter>,
  );
  return merged;
}

describe('PMS guest action regressions', () => {
  beforeEach(() => {
    post.mockReset();
    patch.mockReset();
    post.mockResolvedValue({ data: { ok: true } });
    patch.mockResolvedValue({ data: { status: 'updated' } });
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
    toast.error.mockReset();
    toast.success.mockReset();
  });

  afterEach(() => cleanup());

  it('opens the real booking dialog from a guest card', () => {
    const props = renderGuests();
    fireEvent.click(screen.getByTestId('guest-new-booking-btn-guest-primary'));

    expect(props.setNewBooking).toHaveBeenCalledTimes(1);
    expect(props.setOpenDialog).toHaveBeenCalledWith('booking');
  });

  it('persists guest preferences before reporting success', async () => {
    const props = renderGuests();
    fireEvent.click(screen.getAllByRole('button', { name: 'Tercihler' })[0]);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'TST preference' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(patch).toHaveBeenCalledWith(
      '/pms/guests/guest-primary/preferences',
      expect.objectContaining({
        preferences: expect.objectContaining({ notes: 'TST preference' }),
        preference_notes: 'TST preference',
      }),
    ));
    expect(toast.success).toHaveBeenCalledWith('Misafir tercihleri kaydedildi');
    expect(props.onGuestsChanged).toHaveBeenCalled();
  });

  it('requires confirmation and calls the destructive merge contract once', async () => {
    const props = renderGuests();
    fireEvent.click(screen.getByRole('button', { name: 'Misafir Birleştir' }));
    const selectors = screen.getAllByRole('combobox');
    fireEvent.change(selectors[0], { target: { value: 'guest-primary' } });
    fireEvent.change(selectors[1], { target: { value: 'guest-duplicate' } });
    fireEvent.click(screen.getByRole('button', { name: 'Birleştir' }));

    await waitFor(() => expect(confirmDialog).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'danger' }),
    ));
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/cross-property/guests/guest-primary/merge',
      { target_guest_id: 'guest-duplicate' },
    ));
    expect(post).toHaveBeenCalledTimes(1);
    expect(props.onGuestsChanged).toHaveBeenCalled();
  });

  it('does not merge when the destructive confirmation is cancelled', async () => {
    confirmDialog.mockResolvedValue(false);
    renderGuests();
    fireEvent.click(screen.getByRole('button', { name: 'Misafir Birleştir' }));
    const selectors = screen.getAllByRole('combobox');
    fireEvent.change(selectors[0], { target: { value: 'guest-primary' } });
    fireEvent.change(selectors[1], { target: { value: 'guest-duplicate' } });
    fireEvent.click(screen.getByRole('button', { name: 'Birleştir' }));

    await waitFor(() => expect(confirmDialog).toHaveBeenCalled());
    expect(post).not.toHaveBeenCalled();
  });

  it('does not report preference success when persistence fails', async () => {
    patch.mockRejectedValueOnce({ response: { data: { detail: 'PREFERENCE_WRITE_FAILED' } } });
    renderGuests();
    fireEvent.click(screen.getAllByRole('button', { name: 'Tercihler' })[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('PREFERENCE_WRITE_FAILED'));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows a validation error instead of silently ignoring an incomplete guest', () => {
    render(
      <GuestCreateDialog open onClose={vi.fn()} onGuestCreated={vi.fn()} />,
    );
    const fields = screen.getAllByRole('textbox');
    fireEvent.change(fields[0], { target: { value: 'TST Guest' } });
    fireEvent.change(fields[1], { target: { value: 'tst@example.invalid' } });
    fireEvent.change(fields[2], { target: { value: '0000000000' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Save Guest' }));

    expect(post).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      'Ad soyad, e-posta, telefon ve kimlik/pasaport numarası zorunludur.',
    );
  });

  it('submits a complete guest exactly once', async () => {
    const onClose = vi.fn();
    const onGuestCreated = vi.fn();
    render(
      <GuestCreateDialog open onClose={onClose} onGuestCreated={onGuestCreated} />,
    );
    const fields = screen.getAllByRole('textbox');
    ['TST Guest', 'tst@example.invalid', '0000000000', 'TST-ID'].forEach((value, index) => {
      fireEvent.change(fields[index], { target: { value } });
    });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Save Guest' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith(
      '/pms/guests',
      expect.objectContaining({
        name: 'TST Guest',
        id_number: 'TST-ID',
        kvkk_consent: true,
      }),
      expect.objectContaining({
        headers: { 'Idempotency-Key': expect.any(String) },
      }),
    );
    expect(onClose).toHaveBeenCalled();
    expect(onGuestCreated).toHaveBeenCalled();
  });
});
