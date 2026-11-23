// Test koruması: bugünkü "Folio Yönetimi yavaş açılma + boş kalma" bug fix'inin
// regression olmaması için. FolioViewDialog'un üç durumu net olarak doğrulanır:
//   1) selectedFolio null + folios boş  → loading spinner
//   2) selectedFolio null + folios>1    → folio picker (kullanıcı seçer)
//   3) selectedFolio dolu               → tam folyo UI
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
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

describe('guest-card account detail parity', () => {
  const folio = { id: 'f', booking_id: 'b', folio_number: 'F-105', status: 'open', currency: 'TRY', balance: 50 };
  it('uses the reservation guest when a window has no guest ID and separates service from posting dates', () => {
    render(<FolioViewDialog {...baseProps} selectedFolio={folio}
      bookings={[{ id: 'b', guest_id: 'g', guest_name: 'Ayşe Deniz' }]}
      guests={[{ name: 'Wrong unlinked guest' }]}
      folioCharges={[{ id: 'spa', description: 'Masaj', charge_category: 'spa', total: 120, vat_amount: 20,
        created_at: '2026-11-14T08:00:00Z', service_date: '2026-11-10', service_time: '15:00', service_timing_source: 'spa_appointment' }]} />);
    expect(screen.getByText('Ayşe Deniz')).toBeInTheDocument();
    expect(screen.queryByText('Wrong unlinked guest')).not.toBeInTheDocument();
    expect(screen.getByText(/10.11.2026 · 15:00 \(randevu\)/)).toBeInTheDocument();
    expect(screen.getByText(/Kayıt:/)).toHaveTextContent('14');
    expect(screen.getByText(/KDV \(oran belirtilmemiş\)/)).toBeInTheDocument();
  });
  it('does not duplicate verified inclusive laundry VAT as city tax', () => {
    render(<FolioViewDialog {...baseProps} selectedFolio={folio} folioCharges={[{
      id: 'laundry', charge_category: 'laundry', description: 'Ceket', total: 150,
      amount: 150, net_amount: 125, vat_amount: 25, tax_amount: 25,
      tax_inclusive: true, tax_snapshot: { status: 'verified' },
    }]} />);
    expect(screen.getByText(/KDV \(tutara dahil\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Şehir vergisi:/)).not.toBeInTheDocument();
  });
  it('offers a refund only for eligible receipts and labels offsets and refunds correctly', () => {
    const rows = [
      { id: 'cash', method: 'cash', amount: 100 },
      { id: 'refund', method: 'cash', amount: 20, payment_type: 'refund' },
      { id: 'comp', method: 'discount', amount: 10 },
      { id: 'security', method: 'security_deposit_application', amount: 30 },
      { id: 'pending', method: 'card', amount: 800, status: 'pending' },
      { id: 'external', method: 'card', amount: 100, provider_ref: 'provider-payment' },
      { id: 'sealed', method: 'bank_transfer', amount: 100, can_void: false },
    ];
    render(<FolioViewDialog {...baseProps} selectedFolio={folio} folioPayments={rows} />);
    expect(screen.getAllByRole('button', { name: 'İade' })).toHaveLength(1);
    expect(screen.getByText('Güvence mahsubu (yeni tahsilat değil)')).toBeInTheDocument();
    expect(screen.getByText('İkram / indirim (tahsilat değil)')).toBeInTheDocument();
    expect(screen.getByText('Ödeme iadesi')).toBeInTheDocument();
    expect(screen.getByText(/-₺20,00/)).toBeInTheDocument();
    expect(screen.getByText('Bakiye hesabına dahil değil')).toBeInTheDocument();
  });
  it('shows authoritative net, unknown price/tax details and separate non-cash totals in the proforma', async () => {
    axios.post.mockResolvedValueOnce({ data: { folio, hotel: {}, guest: {}, booking: {},
      charges: [{ id: 'spa', description: 'Masaj', total: 120, amount: 120, net_amount: 100, subtotal: 100, vat_amount: 20, vat_rate: null, service_date: '2026-11-10' }],
      vat_breakdown: [{ vat_rate: null, net: 100, vat_amount: 20 }],
      totals: { grand_total: 120, subtotal: null, net_total: null, vat_total: null, payments_total: 120, collections_total: 80, non_cash_total: 40, opening_balance: 50, balance_due: 50, tax_breakdown_complete: false } } });
    render(<FolioViewDialog {...baseProps} selectedFolio={folio} />);
    fireEvent.click(screen.getByRole('button', { name: 'Proforma Fatura' }));
    const dialog = await screen.findByRole('dialog', { name: 'Proforma Fatura' });
    const row = within(dialog).getByText('Masaj').closest('tr');
    const cells = within(row).getAllByRole('cell');
    expect(cells[0]).toHaveTextContent('10.11.2026');
    expect(cells[2]).toHaveTextContent('—');
    expect(cells[6]).toHaveTextContent('100.00');
    expect(within(dialog).getByText('Oran belirtilmemiş')).toBeInTheDocument();
    expect(within(dialog).getByText('Net tahsilat (iadeler düşüldü)').parentElement).toHaveTextContent('80,00');
    expect(within(dialog).getByText('İkram / cari / güvence mahsupları').parentElement).toHaveTextContent('40,00');
    expect(within(dialog).getByText('Önceki hesap bakiyesi').parentElement).toHaveTextContent('50,00');
    expect(within(dialog).getByText(/Bazı hareketlerin vergi ayrıntısı eksik/)).toBeInTheDocument();
    expect(within(dialog).getByText('Net Toplam').parentElement).toHaveTextContent('—');
    expect(within(dialog).getByText('Hesaplanan KDV').parentElement).toHaveTextContent('—');
  });
});

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

describe('FolioViewDialog transfer intent', () => {
  const source = { id: 'source', folio_number: 'F-SOURCE', booking_id: 'b1', currency: 'TRY', status: 'open', balance: 150 };
  const target = { id: 'target', folio_number: 'F-TARGET', booking_id: 'b2', currency: 'TRY', status: 'open', balance: 0,
    guest_name: 'Barış Kaya', room_number: '105' };

  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    axios.get.mockReset().mockResolvedValue({ data: { folios: [target,
      { ...target, id: 'foreign-currency', folio_number: 'F-USD', currency: 'USD' }] } });
    axios.post.mockReset();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.warning).mockClear();
  });

  const prepareTransfer = async (props = {}) => {
    render(<FolioViewDialog {...baseProps} {...props} selectedFolio={source}
      folioCharges={[{ id: 'parking', description: 'Otopark', total: 150, currency: 'TRY', date: '2026-11-10' }]} />);
    fireEvent.click(screen.getByRole('button', { name: 'İşlem Aktar' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/folio/list', expect.any(Object)));
    const picker = await screen.findByRole('combobox', { name: 'Hedef Folio *' });
    const targetOption = within(picker).getByRole('option', { name: /F-TARGET/ });
    expect(targetOption).toHaveTextContent('Barış Kaya');
    expect(screen.queryByRole('option', { name: /F-USD/ })).toBeNull();
    fireEvent.change(picker, { target: { value: target.id } });
    expect(picker).toHaveValue(target.id);
    fireEvent.click(screen.getByLabelText(/Otopark/));
    fireEvent.change(screen.getByPlaceholderText(/misafir oda değişikliği/), { target: { value: 'Oda hesabının ayrılması' } });
  };

  it('retains one transfer key across an uncertain response', async () => {
    axios.post.mockRejectedValueOnce(new Error('network lost')).mockResolvedValueOnce({ data: {} });
    await prepareTransfer();
    fireEvent.click(screen.getByRole('button', { name: 'Aktar', exact: true }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const first = axios.post.mock.calls[0][1];
    fireEvent.click(screen.getByRole('button', { name: 'Aktar', exact: true }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1][1]).toEqual(first);
    expect(first).toMatchObject({ request_id: expect.any(String), from_folio_id: 'source', to_folio_id: 'target', charge_ids: ['parking'] });
  });

  it('does not turn a committed transfer into a failed draft when the readback fails', async () => {
    axios.post.mockResolvedValue({ data: {} });
    await prepareTransfer({ onChargePosted: vi.fn().mockRejectedValue(new Error('read failed')) });
    fireEvent.click(screen.getByRole('button', { name: 'Aktar', exact: true }));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('İşlem kaydedildi')));
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('does not submit the same transfer twice while its response is pending', async () => {
    let finish;
    axios.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    await prepareTransfer();
    const submit = screen.getByRole('button', { name: 'Aktar', exact: true });
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(axios.post).toHaveBeenCalledTimes(1);
    await act(async () => finish({ data: {} }));
    expect(screen.queryByPlaceholderText(/misafir oda değişikliği/)).toBeNull();
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
