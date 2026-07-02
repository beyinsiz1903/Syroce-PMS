// Test koruması: bugünkü "Folio Yönetimi yavaş açılma + boş kalma" bug fix'inin
// regression olmaması için. FolioViewDialog'un üç durumu net olarak doğrulanır:
//   1) selectedFolio null + folios boş  → loading spinner
//   2) selectedFolio null + folios>1    → folio picker (kullanıcı seçer)
//   3) selectedFolio dolu               → tam folyo UI
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
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
    expect(screen.getByText(/250\.50/)).toBeInTheDocument();

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
    expect(screen.getByText(/1500\.00/)).toBeInTheDocument();
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
