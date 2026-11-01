// Test koruması: bugünkü "Folio Yönetimi yavaş açılma + boş kalma" bug fix'inin
// regression olmaması için. FolioViewDialog'un üç durumu net olarak doğrulanır:
//   1) selectedFolio null + folios boş  → loading spinner
//   2) selectedFolio null + folios>1    → folio picker (kullanıcı seçer)
//   3) selectedFolio dolu               → tam folyo UI
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import axios from 'axios';
import { toast } from 'sonner';
import FolioViewDialog from '@/components/pms/FolioViewDialog';

// react-i18next: useTranslation sadece (key, fallback) döner
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key, fallback) => fallback || _key }),
}));

// Sub-dialog tetiklenmesin diye sonner toast'ı mock'la
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

// Axios: dialog içi yan etkiler tetiklenirse hata atmasın
vi.mock('axios', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
}));

const noop = () => {};

const baseProps = {
  open: true,
  onClose: noop,
  folioCharges: [],
  folioPayments: [],
  guests: [],
  bookings: [],
  onChargePosted: noop,
  onPaymentPosted: noop,
};

afterEach(() => cleanup());

describe('FolioViewDialog — empty/loading/picker states', () => {
  it('open=false: dialog DOM\'da görünmez', () => {
    render(
      <FolioViewDialog
        {...baseProps}
        open={false}
        selectedFolio={null}
        folios={[]}
      />
    );
    expect(screen.queryByText(/Folyo Yönetimi/i)).toBeNull();
  });

  it('selectedFolio=null + folios=[] + isLoading=true → loading state ("Folyo yükleniyor…")', () => {
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={null}
        folios={[]}
        isLoading={true}
      />
    );
    // Loader testid + mesaj
    expect(screen.getByTestId('folio-loading')).toBeInTheDocument();
    expect(screen.getByText(/Folyo yükleniyor/i)).toBeInTheDocument();
    // Picker görünmemeli
    expect(screen.queryByTestId('folio-picker')).toBeNull();
  });

  it('selectedFolio=null + folios=[] + isLoading=false → empty state ("Folyo Bulunamadı")', () => {
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={null}
        folios={[]}
        isLoading={false}
      />
    );
    expect(screen.getByTestId('folio-empty')).toBeInTheDocument();
    expect(screen.getByText(/Folyo Bulunamadı/i)).toBeInTheDocument();
    expect(screen.queryByTestId('folio-loading')).toBeNull();
  });

  it('selectedFolio=null + folios>1 → folio picker render eder, butona tıklayınca onPickFolio tetiklenir', () => {
    const onPickFolio = vi.fn();
    const folios = [
      { id: 'f1', folio_number: 'F-001', folio_type: 'guest', balance: 250.5 },
      { id: 'f2', folio_number: 'F-002', folio_type: 'master', balance: 0 },
    ];
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={null}
        folios={folios}
        onPickFolio={onPickFolio}
      />
    );
    expect(screen.getByTestId('folio-picker')).toBeInTheDocument();
    expect(screen.getByText(/F-001/)).toBeInTheDocument();
    expect(screen.getByText(/F-002/)).toBeInTheDocument();
    expect(screen.getByText(/250,50/)).toBeInTheDocument();

    // F-002'ye tıkla → onPickFolio('f2') çağrılmalı
    fireEvent.click(screen.getByText(/F-002/).closest('button'));
    expect(onPickFolio).toHaveBeenCalledWith('f2');
  });

  it('picker: onPickFolio prop yoksa tıklama çakılmadan no-op', () => {
    const folios = [{ id: 'f1', folio_number: 'F-001', folio_type: 'guest', balance: 0 }];
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={null}
        folios={folios}
        // onPickFolio kasten verilmedi
      />
    );
    expect(() => {
      fireEvent.click(screen.getByText(/F-001/).closest('button'));
    }).not.toThrow();
  });

  it('selectedFolio dolu → loading/picker görünmez, tam folyo UI çıkar', () => {
    const selectedFolio = {
      id: 'f1',
      folio_number: 'F-100',
      folio_type: 'guest',
      guest_id: 'g1',
      booking_id: 'b1',
      balance: 1500,
    };
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={selectedFolio}
        folios={[selectedFolio]}
        guests={[{ id: 'g1', name: 'Ali Yılmaz' }]}
        bookings={[{ id: 'b1', check_in: '2026-05-10', check_out: '2026-05-12' }]}
      />
    );
    // Loading/picker DOM'da OLMAMALI
    expect(screen.queryByTestId('folio-loading')).toBeNull();
    expect(screen.queryByTestId('folio-picker')).toBeNull();
    // Misafir adı + bakiye + folio numarası görünmeli
    expect(screen.getByText('Ali Yılmaz')).toBeInTheDocument();
    expect(screen.getByText(/1\.500,00/)).toBeInTheDocument();
    expect(screen.getByText(/F-100/)).toBeInTheDocument();
  });

  it('selectedFolio.balance=0 → "Dengeli" mesajı (ne misafir ne otel borçlu)', () => {
    const selectedFolio = {
      id: 'f1',
      folio_number: 'F-200',
      folio_type: 'guest',
      balance: 0,
    };
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={selectedFolio}
        folios={[selectedFolio]}
      />
    );
    expect(screen.getByText(/Dengeli/i)).toBeInTheDocument();
  });

  it('selectedFolio.balance>0 → "Tahsilat Bekliyor" + kırmızı', () => {
    const selectedFolio = { id: 'f1', folio_number: 'F-X', folio_type: 'guest', balance: 100 };
    render(
      <FolioViewDialog
        {...baseProps}
        selectedFolio={selectedFolio}
        folios={[selectedFolio]}
      />
    );
    expect(screen.getByText(/Tahsilat Bekliyor/i)).toBeInTheDocument();
  });

  it('folios prop default=[] (geriye dönük uyumluluk: prop verilmezse crash yok)', () => {
    expect(() =>
      render(
        <FolioViewDialog
          {...baseProps}
          selectedFolio={null}
          // folios kasten verilmedi
        />
      )
    ).not.toThrow();
    expect(screen.getByTestId('folio-empty')).toBeInTheDocument();
  });
});

describe('FolioViewDialog — receipt write safety', () => {
  const folio = { id: 'receipt-1', booking_id: 'booking-1', folio_number: 'F-300', status: 'open', currency: 'TRY', balance: 100 };
  const mountPayment = (selectedFolio = folio) => {
    const view = render(<FolioViewDialog {...baseProps} selectedFolio={selectedFolio} folios={[selectedFolio]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Ödeme Ekle' }));
    return view;
  };
  const submit = () => fireEvent.submit(screen.getByRole('button', { name: 'Kaydet' }).closest('form'));
  beforeEach(() => {
    axios.post.mockReset().mockResolvedValue({ data: {} });
    vi.mocked(toast.error).mockClear();
  });

  it('sends a strict Turkish decimal in the selected folio currency with an intent key', async () => {
    mountPayment();
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '10,25' } });
    submit();
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0]).toEqual(['/folio/receipt-1/payment', expect.objectContaining({ amount: 10.25, currency: 'TRY' }),
      { headers: { 'Idempotency-Key': expect.any(String) } }]);
  });

  it('requires a verified TRY reporting rate for foreign receipts, with no 1:1 default', async () => {
    mountPayment({ ...folio, currency: 'EUR' });
    fireEvent.change(screen.getByLabelText('Tutar (EUR)'), { target: { value: '10,25' } });
    submit();
    expect(axios.post).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('TL kasa kuru (1 EUR = kaç TRY?)'), { target: { value: '50,25' } });
    submit();
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0][1]).toMatchObject({ currency: 'EUR', amount: 10.25, received_to_try_rate: 50.25 });
  });

  it('does not submit zero, partial or exponent money input', () => {
    mountPayment();
    for (const value of ['0', '10abc', '1e2', '10,']) {
      fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value } });
      submit();
    }
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('blocks a double submit while the first receipt is pending', async () => {
    let finish;
    axios.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    mountPayment();
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '10' } });
    const form = screen.getByRole('button', { name: 'Kaydet' }).closest('form');
    fireEvent.submit(form); fireEvent.submit(form);
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'İşleniyor…' })).toBeDisabled();
    await act(async () => finish({ data: {} }));
  });

  it('reuses a receipt intent after an uncertain response and refuses changed money', async () => {
    axios.post.mockRejectedValue(new Error('Bağlantı kesildi'));
    const view = mountPayment();
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '10' } });
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const originalKey = axios.post.mock.calls[0][2].headers['Idempotency-Key'];
    view.rerender(<FolioViewDialog {...baseProps} selectedFolio={{ ...folio, balance: 0 }} />);
    submit();
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kaydet' })).toBeEnabled());
    expect(axios.post.mock.calls[1][2].headers['Idempotency-Key']).toBe(originalKey);
    expect(axios.post.mock.calls[1][1].payment_type).toBe(axios.post.mock.calls[0][1].payment_type);
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '20' } });
    submit();
    await waitFor(() => expect(toast.error).toHaveBeenLastCalledWith(expect.stringContaining('sonucu belirsiz')));
    expect(axios.post).toHaveBeenCalledTimes(2);
  });

  it('does not offer new charges or receipts on a closed folio', () => {
    render(<FolioViewDialog {...baseProps} selectedFolio={{ ...folio, status: 'closed' }} />);
    expect(screen.getByRole('button', { name: 'Ödeme Ekle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'İşlem Ekle' })).toBeDisabled();
  });

  it('does not leave a paid-looking failure draft when the refresh callback fails', async () => {
    render(<FolioViewDialog {...baseProps} selectedFolio={folio} onPaymentPosted={vi.fn().mockRejectedValue(new Error('read unavailable'))} />);
    fireEvent.click(screen.getByRole('button', { name: 'Ödeme Ekle' }));
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '10' } });
    submit();
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('İşlem kaydedildi')));
    expect(screen.queryByLabelText('Tutar (TRY)')).not.toBeInTheDocument();
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('closes the old draft when the selected folio window changes', () => {
    const view = mountPayment();
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '10' } });
    view.rerender(<FolioViewDialog {...baseProps} selectedFolio={{ ...folio, id: 'receipt-2', currency: 'EUR' }} />);
    expect(screen.queryByLabelText('Tutar (TRY)')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ödeme Ekle' }));
    expect(screen.getByLabelText('Tutar (EUR)')).toHaveValue('0');
  });
});
