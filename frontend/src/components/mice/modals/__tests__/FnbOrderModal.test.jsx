// Test koruması: FnbOrderModal'ın sipariş yaşam döngüsü (sent → acknowledged →
// completed) butonlarının regresyona uğramaması için. Doğrulanan davranışlar:
//   1) Sipariş listesi durum rozetleriyle render edilir
//      (Gönderildi / Onaylandı / Tamamlandı)
//   2) "Onayla" tıklaması transition uç noktasını status=acknowledged ile çağırır
//      "Tamamla" tıklaması transition uç noktasını status=completed ile çağırır
//   3) 409 yanıtında backend'in Türkçe detail mesajı toast ile gösterilir ve
//      sipariş listesi yeniden yüklenir
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, fireEvent, cleanup, waitFor,
} from '@testing-library/react';
import axios from 'axios';
import { toast } from 'sonner';
import FnbOrderModal from '@/components/mice/modals/FnbOrderModal';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

// promptDialog tetiklenmesin diye (Mutfağa Gönder akışı bu testlerde kullanılmaz)
vi.mock('@/lib/dialogs', () => ({
  promptDialog: vi.fn().mockResolvedValue('not used'),
}));

const event = {
  id: 'evt-1',
  name: 'Düğün Resepsiyonu',
  status: 'confirmed',
  expected_pax: 120,
  resources: [{ type: 'fb' }, { type: 'fb' }],
};

const makeOrder = (over = {}) => ({
  id: 'ord-1',
  status: 'sent',
  target: 'kitchen',
  total: 5000,
  lines: [{ name: 'Ana yemek' }],
  expected_pax: 120,
  sent_by: 'ayse',
  sent_at: '2026-06-10T18:30:00',
  note: null,
  ...over,
});

const ordersResponse = (orders) => ({ data: { orders } });

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => cleanup());

describe('FnbOrderModal — sipariş yaşam döngüsü', () => {
  it('sipariş listesini durum rozetleriyle render eder (Gönderildi/Onaylandı/Tamamlandı)', async () => {
    axios.get.mockResolvedValueOnce(ordersResponse([
      makeOrder({ id: 'o-sent', status: 'sent' }),
      makeOrder({ id: 'o-ack', status: 'acknowledged', acknowledged_by: 'mehmet', acknowledged_at: '2026-06-10T18:40:00' }),
      makeOrder({ id: 'o-done', status: 'completed', completed_by: 'mehmet', completed_at: '2026-06-10T19:10:00' }),
    ]));

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    expect(await screen.findByText('Gönderildi')).toBeInTheDocument();
    expect(screen.getByText('Onaylandı')).toBeInTheDocument();
    expect(screen.getByText('Tamamlandı')).toBeInTheDocument();

    // sent → "Onayla" butonu, acknowledged → "Tamamla" butonu, completed → buton yok
    expect(screen.getByRole('button', { name: /Onayla/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Tamamla/i })).toBeInTheDocument();
  });

  it('"Onayla" tıklaması transition uç noktasını status=acknowledged ile çağırır', async () => {
    axios.get.mockResolvedValue(ordersResponse([makeOrder({ id: 'o-sent', status: 'sent' })]));
    axios.post.mockResolvedValueOnce({ data: {} });

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const ackBtn = await screen.findByRole('button', { name: /Onayla/i });
    fireEvent.click(ackBtn);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        '/mice/events/evt-1/fnb-orders/o-sent/transition',
        { status: 'acknowledged' },
      );
    });
    expect(toast.success).toHaveBeenCalledWith('Sipariş onaylandı (mutfak teslim aldı)');
  });

  it('"Tamamla" tıklaması transition uç noktasını status=completed ile çağırır', async () => {
    axios.get.mockResolvedValue(ordersResponse([makeOrder({ id: 'o-ack', status: 'acknowledged' })]));
    axios.post.mockResolvedValueOnce({ data: {} });

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const doneBtn = await screen.findByRole('button', { name: /Tamamla/i });
    fireEvent.click(doneBtn);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        '/mice/events/evt-1/fnb-orders/o-ack/transition',
        { status: 'completed' },
      );
    });
    expect(toast.success).toHaveBeenCalledWith('Sipariş tamamlandı');
  });

  it('409 yanıtında backend Türkçe detail mesajını toast ile gösterir ve listeyi yeniden yükler', async () => {
    // İlk yükleme: sipariş "sent" → Onayla butonu görünür
    axios.get.mockResolvedValueOnce(ordersResponse([makeOrder({ id: 'o-sent', status: 'sent' })]));
    // Reload (409 sonrası): backend gerçek durumu "acknowledged" döner
    axios.get.mockResolvedValueOnce(ordersResponse([makeOrder({ id: 'o-sent', status: 'acknowledged' })]));

    axios.post.mockRejectedValueOnce({
      response: { status: 409, data: { detail: 'Sipariş zaten onaylanmış durumda' } },
    });

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const ackBtn = await screen.findByRole('button', { name: /Onayla/i });
    fireEvent.click(ackBtn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Sipariş zaten onaylanmış durumda');
    });

    // 409 sonrası liste yeniden yüklenmeli (ilk mount + reload = 2 GET)
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledTimes(2);
    });
    // Reload sonrası gerçek durum yansır: artık "Tamamla" görünür, "Onayla" yok
    expect(await screen.findByRole('button', { name: /Tamamla/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Onayla/i })).toBeNull();
  });
});
