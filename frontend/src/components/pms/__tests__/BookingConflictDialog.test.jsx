// Test koruması: BookingConflictDialog'un structured 409 payload'ı için
// dialog UI'ını (toast yerine) render ettiğini doğrular. Regression olursa
// (örn. parent yanlışlıkla parser bypass edip toast'a düşerse) bu testler
// kırılır. Full-detail + available-rooms axios çağrıları mock'lanır.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

const axiosGet = vi.fn();
vi.mock('axios', () => ({
  default: { get: (...args) => axiosGet(...args) },
}));

import BookingConflictDialog from '@/components/pms/BookingConflictDialog';

const conflict = {
  message: 'Oda 101 bu tarihlerde dolu',
  conflictingBookingId: 'bk-123',
  conflictType: 'room_double_book',
  conflictWindow: {
    room_id: 'room-1',
    check_in: '2026-06-01',
    check_out: '2026-06-03',
  },
};

const fullDetailResponse = {
  data: {
    guest: { name: 'Ali Yılmaz' },
    room: { room_number: '101' },
    booking: {
      check_in: '2026-06-01',
      check_out: '2026-06-03',
      status: 'checked_in',
    },
  },
};

const availableRoomsResponse = {
  data: {
    available_rooms: [
      { id: 'r2', room_number: '202', room_type: 'Deluxe', is_same_type: true, price_per_night: 1500 },
      { id: 'r3', room_number: '305', room_type: 'Suite', is_same_type: false, price_per_night: 2500 },
    ],
  },
};

function setupAxios({ fullDetail = fullDetailResponse, available = availableRoomsResponse } = {}) {
  axiosGet.mockImplementation((url) => {
    if (url.includes('/full-detail')) {
      return fullDetail instanceof Error ? Promise.reject(fullDetail) : Promise.resolve(fullDetail);
    }
    if (url.includes('/available-rooms')) {
      return available instanceof Error ? Promise.reject(available) : Promise.resolve(available);
    }
    return Promise.resolve({ data: {} });
  });
}

function renderDialog(props = {}) {
  return render(
    <MemoryRouter>
      <BookingConflictDialog
        conflict={conflict}
        open
        onClose={() => {}}
        {...props}
      />
    </MemoryRouter>
  );
}

beforeEach(() => {
  axiosGet.mockReset();
  navigateMock.mockReset();
});
afterEach(() => cleanup());

describe('BookingConflictDialog', () => {
  it('open=false: dialog DOM\'a basılmaz', () => {
    setupAxios();
    renderDialog({ open: false });
    expect(screen.queryByTestId('booking-conflict-dialog')).toBeNull();
  });

  it('conflict=null: hiçbir şey render etmez', () => {
    setupAxios();
    render(
      <MemoryRouter>
        <BookingConflictDialog conflict={null} open onClose={() => {}} />
      </MemoryRouter>
    );
    expect(screen.queryByTestId('booking-conflict-dialog')).toBeNull();
  });

  it('structured conflict: dialog açılır, mesaj + blocker misafir/oda/tarih + alternatifler render olur', async () => {
    setupAxios();
    renderDialog();

    // Dialog mount + statik mesaj
    expect(await screen.findByTestId('booking-conflict-dialog')).toBeInTheDocument();
    expect(screen.getByText('Oda 101 bu tarihlerde dolu')).toBeInTheDocument();

    // Full-detail + available-rooms doğru URL'lerle çağrıldı
    await waitFor(() => {
      expect(axiosGet).toHaveBeenCalledWith('/pms/reservations/bk-123/full-detail');
      expect(axiosGet).toHaveBeenCalledWith('/bookings/bk-123/available-rooms');
    });

    // Blocker bilgileri
    expect(await screen.findByTestId('conflict-blocker-guest')).toHaveTextContent('Ali Yılmaz');
    expect(screen.getByTestId('conflict-blocker-room')).toHaveTextContent(/101/);
    expect(screen.getByTestId('conflict-blocker-dates')).toBeInTheDocument();

    // Alternatifler listesi (2 oda)
    const list = await screen.findByTestId('conflict-alternatives-list');
    expect(list).toBeInTheDocument();
    expect(screen.getByTestId('conflict-alt-r2')).toHaveTextContent(/202/);
    expect(screen.getByTestId('conflict-alt-r3')).toHaveTextContent(/305/);

    // "Diğer rezervasyonu aç" butonu
    expect(screen.getByTestId('conflict-view-other')).toBeInTheDocument();
  });

  it('"Diğer rezervasyonu aç" butonu onClose + navigate çağırır', async () => {
    setupAxios();
    const onClose = vi.fn();
    renderDialog({ onClose });

    const btn = await screen.findByTestId('conflict-view-other');
    fireEvent.click(btn);

    expect(onClose).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/app/pms?edit=bk-123#bookings');
  });

  it('onPickAlternative verilirse her alternatif satırında "Bu odayı seç" butonu çıkar ve tıklayınca callback çağrılır', async () => {
    setupAxios();
    const onPickAlternative = vi.fn();
    renderDialog({ onPickAlternative });

    const pickBtn = await screen.findByTestId('conflict-alt-pick-r2');
    fireEvent.click(pickBtn);

    expect(onPickAlternative).toHaveBeenCalledTimes(1);
    expect(onPickAlternative).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r2', room_number: '202' })
    );
  });

  it('onPickAlternative verilmezse "Bu odayı seç" butonları render olmaz', async () => {
    setupAxios();
    renderDialog();
    await screen.findByTestId('conflict-alternatives-list');
    expect(screen.queryByTestId('conflict-alt-pick-r2')).toBeNull();
    expect(screen.queryByTestId('conflict-alt-pick-r3')).toBeNull();
  });

  it('available-rooms boş döner: "uygun başka oda bulunamadı" mesajı görünür', async () => {
    setupAxios({ available: { data: { available_rooms: [] } } });
    renderDialog();
    expect(await screen.findByTestId('conflict-alternatives-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('conflict-alternatives-list')).toBeNull();
  });

  it('full-detail 403/404 ile reddedilirse fallback: conflictWindow.room_id görünür, crash yok', async () => {
    setupAxios({ fullDetail: new Error('forbidden') });
    renderDialog();
    // Fallback blocker bilgisi conflictWindow'dan üretildi
    await waitFor(() => {
      expect(screen.getByTestId('conflict-blocker-room')).toHaveTextContent(/room-1/);
    });
    // Misafir adı alınamadı mesajı
    expect(screen.getByTestId('conflict-blocker-guest')).toHaveTextContent(/alınamadı/i);
  });

  it('conflictingBookingId yoksa: full-detail/available-rooms çağrılmaz ve "Diğer rezervasyonu aç" butonu çıkmaz', async () => {
    setupAxios();
    renderDialog({
      conflict: { ...conflict, conflictingBookingId: null },
    });
    expect(await screen.findByTestId('booking-conflict-dialog')).toBeInTheDocument();
    expect(axiosGet).not.toHaveBeenCalled();
    expect(screen.queryByTestId('conflict-view-other')).toBeNull();
  });
});
