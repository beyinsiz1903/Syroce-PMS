// Test koruması: FnbOrderModal'ın sipariş yaşam döngüsü (sent → acknowledged →
// completed) butonlarının regresyona uğramaması için. Doğrulanan davranışlar:
//   1) Sipariş listesi durum rozetleriyle render edilir
//      (Gönderildi / Onaylandı / Tamamlandı)
//   2) "Onayla" tıklaması transition uç noktasını status=acknowledged ile çağırır
//      "Tamamla" tıklaması transition uç noktasını status=completed ile çağırır
//   3) 409 yanıtında backend'in Türkçe detail mesajı toast ile gösterilir ve
//      sipariş listesi yeniden yüklenir
//   4) "Mutfağa Gönder" akışı (Görev #312): buton yalnızca uygun koşullarda
//      etkin; tıklama promptDialog açar, dönen notla Idempotency-Key başlığı
//      ile POST .../fnb-order/send çağrılır; hata detail'i toast ile gösterilir
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, fireEvent, cleanup, waitFor,
} from '@testing-library/react';
import axios from 'axios';
import { toast } from 'sonner';
import { promptDialog } from '@/lib/dialogs';
import FnbOrderModal from '@/components/mice/modals/FnbOrderModal';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

// promptDialog testlerde tek tek kontrol edilir (mockResolvedValueOnce).
// Varsayılan: null (iptal) → yaşam döngüsü testlerinde sendToKitchen tetiklense
// bile POST yapılmaz.
vi.mock('@/lib/dialogs', () => ({
  promptDialog: vi.fn().mockResolvedValue(null),
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

describe('FnbOrderModal — Mutfağa Gönder akışı', () => {
  it('"Mutfağa Gönder" butonu uygun koşullarda (durum uygun + F&B satırı > 0) etkindir', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    await screen.findByText('Henüz mutfağa sipariş gönderilmemiş.');
    expect(screen.getByRole('button', { name: /Mutfağa Gönder/i })).toBeEnabled();
  });

  it('"Mutfağa Gönder" butonu etkinlik durumu uygun değilse devre dışıdır', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));

    render(
      <FnbOrderModal event={{ ...event, status: 'cancelled' }} onClose={() => {}} />,
    );

    await screen.findByText('Henüz mutfağa sipariş gönderilmemiş.');
    expect(screen.getByRole('button', { name: /Mutfağa Gönder/i })).toBeDisabled();
  });

  it('"Mutfağa Gönder" butonu F&B satırı yoksa devre dışıdır', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));

    render(
      <FnbOrderModal event={{ ...event, resources: [] }} onClose={() => {}} />,
    );

    await screen.findByText('Henüz mutfağa sipariş gönderilmemiş.');
    expect(screen.getByRole('button', { name: /Mutfağa Gönder/i })).toBeDisabled();
  });

  it('tıklama promptDialog açar, dönen notla Idempotency-Key başlığı ile POST .../fnb-order/send çağırır', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));
    axios.post.mockResolvedValueOnce({ data: {} });
    promptDialog.mockResolvedValueOnce('Servis 19:00, glutensiz 5 pax');

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const sendBtn = await screen.findByRole('button', { name: /Mutfağa Gönder/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(promptDialog).toHaveBeenCalledTimes(1);
    });
    expect(promptDialog).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Mutfağa Gönder', confirmText: 'Gönder' }),
    );

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledTimes(1);
    });
    const [url, body, config] = axios.post.mock.calls[0];
    expect(url).toBe('/mice/events/evt-1/fnb-order/send');
    expect(body).toEqual({ target: 'kitchen', note: 'Servis 19:00, glutensiz 5 pax' });
    expect(config.headers['Idempotency-Key']).toEqual(expect.any(String));
    expect(config.headers['Idempotency-Key'].length).toBeGreaterThan(0);

    expect(toast.success).toHaveBeenCalledWith('F&B siparişi mutfağa gönderildi');
  });

  it('boş not girilirse POST body note=null olarak gönderilir', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));
    axios.post.mockResolvedValueOnce({ data: {} });
    promptDialog.mockResolvedValueOnce('');

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const sendBtn = await screen.findByRole('button', { name: /Mutfağa Gönder/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledTimes(1);
    });
    const [, body] = axios.post.mock.calls[0];
    expect(body).toEqual({ target: 'kitchen', note: null });
  });

  it('promptDialog iptal edilirse (null) POST yapılmaz', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));
    promptDialog.mockResolvedValueOnce(null);

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const sendBtn = await screen.findByRole('button', { name: /Mutfağa Gönder/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(promptDialog).toHaveBeenCalledTimes(1);
    });
    expect(axios.post).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('hata durumunda backend detail mesajı toast ile gösterilir', async () => {
    axios.get.mockResolvedValue(ordersResponse([]));
    promptDialog.mockResolvedValueOnce('acele');
    axios.post.mockRejectedValueOnce({
      response: { status: 400, data: { detail: 'Bu etkinlik için sipariş gönderilemez' } },
    });

    render(<FnbOrderModal event={event} onClose={() => {}} />);

    const sendBtn = await screen.findByRole('button', { name: /Mutfağa Gönder/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Bu etkinlik için sipariş gönderilemez');
    });
  });
});
