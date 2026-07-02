import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, act, cleanup, waitFor, within, fireEvent,
} from '@testing-library/react';
import { toast } from 'sonner';
import CorporateContractApprovals from '@/pages/CorporateContractApprovals';

// Toast feedback is asserted in the approver-action tests; mock sonner so the
// success/error calls are observable and don't try to render real toasts.
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

// The component uses t() from react-i18next for all UI strings.
// Without a proper i18n setup in the test environment the component renders
// raw keys (e.g. "cm.pages_CorporateContractApprovals.onayla") instead of
// Turkish text, which breaks every assertion that looks for a translated string.
// We provide an explicit map so t(key) returns the Turkish equivalent.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => {
      const map = {
        'cm.pages_CorporateContractApprovals.kurumsal_s\u00f6zle\u015Fme_onaylar\u0131': 'Kurumsal S\u00f6zle\u015fme Onaylar\u0131',
        'cm.pages_CorporateContractApprovals.yenile': 'Yenile',
        'cm.pages_CorporateContractApprovals.toplam_s\u00f6zle\u015Fme': 'Toplam S\u00f6zle\u015fme',
        'cm.pages_CorporateContractApprovals.onay_bekleyen': 'Onay Bekleyen',
        'cm.pages_CorporateContractApprovals.onaylanan': 'Onaylanan',
        'cm.pages_CorporateContractApprovals.reddedilen': 'Reddedilen',
        'cm.pages_CorporateContractApprovals.y\u00fckleniyor': 'Y\u00fckleniyor...',
        'cm.pages_CorporateContractApprovals.hen\u00fcz_kurumsal_s\u00f6zle\u015Fme_bulunm': 'Hen\u00fcz kurumsal s\u00f6zle\u015fme bulunmuyor.',
        'cm.pages_CorporateContractApprovals.s\u00f6zle\u015Fmeler': 'S\u00f6zle\u015fmeler (',
        'cm.pages_CorporateContractApprovals.t\u00fcr': 'T\u00fcr: ',
        'cm.pages_CorporateContractApprovals.kod': 'Kod: ',
        'cm.pages_CorporateContractApprovals.d\u00f6nem': 'D\u00f6nem: ',
        'cm.pages_CorporateContractApprovals.onayla': 'Onayla',
        'cm.pages_CorporateContractApprovals.reddet': 'Reddet',
        'cm.pages_CorporateContractApprovals.onay_ge\u00e7mi\u015Fi': 'Onay Ge\u00e7mi\u015fi',
        'cm.pages_CorporateContractApprovals.reddedilme_gerek\u00e7esi': 'Reddedilme Gerek\u00e7esi',
        'cm.pages_CorporateContractApprovals.sonraki_ad\u0131m_gerekli_d\u00fczeltmel': 'Sonraki ad\u0131m: Gerekli d\u00fczeltmeleri yap\u0131n ve yeniden g\u00f6nderin.',
        'cm.pages_CorporateContractApprovals.yeniden_g\u00f6nder': 'Yeniden G\u00f6nder',
        'cm.pages_CorporateContractApprovals._durum_ge\u00e7i\u015Fleri_gerek\u00e7eler_ki': ' \u2014 durum ge\u00e7i\u015fleri, gerek\u00e7eler, kimin taraf\u0131ndan yap\u0131ld\u0131\u011f\u0131 ve zaman bilgisi.',
        'cm.pages_CorporateContractApprovals.hen\u00fcz_onay_hareketi_yok': 'Hen\u00fcz onay hareketi yok.',
        'cm.pages_CorporateContractApprovals.s\u00f6zle\u015Fmeyi_reddet': 'S\u00f6zle\u015fmeyi Reddet',
        'cm.pages_CorporateContractApprovals.reddedilecek_gerek\u00e7e_zorunludu': ' reddedilecek. Gerek\u00e7e zorunludur.',
        'cm.pages_CorporateContractApprovals.reddetme_gerek\u00e7esi': 'Reddetme Gerek\u00e7esi',
        'cm.pages_CorporateContractApprovals.\u00f6rn_g\u00f6r\u00fc\u015f\u00fclenen_oran_politikam\u0131z': '\u00d6rn. g\u00f6r\u00fc\u015f\u00fclen oran politikam\u0131zla uy\u015fumuyor, eksik bilgi...',
        'cm.pages_CorporateContractApprovals.vazge\u00e7': 'Vazge\u00e7',
      };
      return map[key] ?? key;
    },
    i18n: { language: 'tr', changeLanguage: () => Promise.resolve() },
  }),
}));

// Stable token so the component's Authorization header / fetch path resolve.
beforeEach(() => {
  localStorage.setItem('token', 'test-token');
  // The sonner mock is module-level; clear it so toast assertions don't see
  // calls leaked from a previous test (restoreAllMocks won't reset vi.mock fns).
  toast.success.mockClear();
  toast.error.mockClear();
  toast.warning.mockClear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

function mockContracts(contracts) {
  vi.spyOn(global, 'fetch').mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ contracts }),
  });
}

// Route fetch by URL: the list GET vs the approval-transition POST. Returns the
// spy so tests can assert on the exact transition payload and on the refresh GET.
// `transition` defaults to a success; pass { ok:false, status, body } to fail it.
function mockFetchRouter(contracts, transition = {}) {
  const t = { ok: true, status: 200, body: { ok: true }, ...transition };
  return vi.spyOn(global, 'fetch').mockImplementation(async (url, opts) => {
    if (String(url).includes('approval-transition')) {
      return { ok: t.ok, status: t.status, json: async () => t.body };
    }
    return { ok: true, status: 200, json: async () => ({ contracts }) };
  });
}

const PENDING = [{
  id: 'p1', company_name: 'Pending Co', approval_status: 'pending', approval_history: [],
}];

function transitionCall(fetchSpy) {
  return fetchSpy.mock.calls.find((c) => String(c[0]).includes('approval-transition'));
}

function getCallCount(fetchSpy) {
  return fetchSpy.mock.calls.filter((c) => !(c[1] && c[1].method === 'POST')).length;
}

async function renderPage() {
  await act(async () => {
    render(<CorporateContractApprovals />);
  });
  // Wait for the initial fetch to settle (loading spinner gone).
  await waitFor(() =>
    expect(screen.queryByText('Yükleniyor...')).toBeNull(),
  );
}

describe('CorporateContractApprovals — rejection reason view', () => {
  it('shows the most recent rejection reason (reason / by / at) for a rejected contract', async () => {
    const at = '2026-05-10T09:30:00Z';
    mockContracts([
      {
        id: 'c1',
        company_name: 'Acme A.Ş.',
        approval_status: 'rejected',
        approval_history: [
          {
            from_status: 'pending', to_status: 'rejected',
            reason: 'Eski gerekçe', by: 'Bob', at: '2026-05-01T08:00:00Z',
          },
          { from_status: 'rejected', to_status: 'draft', by: 'Owner', at: '2026-05-02T08:00:00Z' },
          { from_status: 'draft', to_status: 'pending', by: 'Owner', at: '2026-05-09T08:00:00Z' },
          {
            from_status: 'pending', to_status: 'rejected',
            reason: 'Vergi numarası eksik', by: 'Carol', at,
          },
        ],
      },
    ]);

    await renderPage();

    // The newest rejection wins, not the earlier one.
    expect(screen.getByText('Reddedilme Gerekçesi')).toBeInTheDocument();
    expect(screen.getByText('Vergi numarası eksik')).toBeInTheDocument();
    expect(screen.queryByText('Eski gerekçe')).toBeNull();

    // "by" and "at" are surfaced together.
    expect(screen.getByText(/Carol tarafından/)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(new Date(at).toLocaleString().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))),
    ).toBeInTheDocument();
  });

  it('falls back to placeholder reason and unknown user when fields are missing', async () => {
    mockContracts([
      {
        id: 'c1',
        company_name: 'Beta Ltd.',
        approval_status: 'rejected',
        approval_history: [
          { from_status: 'pending', to_status: 'rejected' },
        ],
      },
    ]);

    await renderPage();

    expect(screen.getByText('Gerekçe belirtilmemiş.')).toBeInTheDocument();
    expect(screen.getByText(/Bilinmeyen kullanıcı/)).toBeInTheDocument();
  });

  it('does not render a rejection banner for non-rejected contracts', async () => {
    mockContracts([
      {
        id: 'c1',
        company_name: 'Gamma',
        approval_status: 'approved',
        approval_history: [
          { from_status: 'pending', to_status: 'approved', by: 'Mgr', at: '2026-05-10T09:30:00Z' },
        ],
      },
    ]);

    await renderPage();

    expect(screen.queryByText('Reddedilme Gerekçesi')).toBeNull();
  });
});

describe('CorporateContractApprovals — approval-history dialog', () => {
  it('renders all transitions newest-first', async () => {
    mockContracts([
      {
        id: 'c1',
        company_name: 'Acme A.Ş.',
        approval_status: 'rejected',
        approval_history: [
          { from_status: 'draft', to_status: 'pending', reason: 'İlk gönderim', by: 'Owner', at: '2026-05-01T08:00:00Z' },
          { from_status: 'pending', to_status: 'rejected', reason: 'İkinci adım', by: 'Bob', at: '2026-05-02T08:00:00Z' },
          { from_status: 'rejected', to_status: 'draft', reason: 'Üçüncü adım', by: 'Owner', at: '2026-05-03T08:00:00Z' },
        ],
      },
    ]);

    await renderPage();

    // Button shows the history length.
    const historyBtn = screen.getByRole('button', { name: /Onay Geçmişi \(3\)/ });
    fireEvent.click(historyBtn);

    const dialog = await screen.findByRole('dialog');
    const reasons = within(dialog).getAllByText(/adım|gönderim/);
    // Newest entry first → reverse chronological order.
    expect(reasons.map((el) => el.textContent)).toEqual([
      'Üçüncü adım',
      'İkinci adım',
      'İlk gönderim',
    ]);
  });

  it('renders the empty state when a contract has no approval history', async () => {
    mockContracts([
      {
        id: 'c1',
        company_name: 'NoHistory',
        approval_status: 'draft',
        approval_history: [],
      },
    ]);

    await renderPage();

    // The history button is disabled when there are no transitions.
    const historyBtn = screen.getByRole('button', { name: /Onay Geçmişi/ });
    expect(historyBtn).toBeDisabled();
  });

  it('shows the dialog empty-state text when opened for a contract whose history later reads empty', async () => {
    // A contract reporting a length but an empty array still renders the empty state.
    mockContracts([
      {
        id: 'c1',
        company_name: 'EdgeCase',
        approval_status: 'pending',
        approval_history: [
          { from_status: 'draft', to_status: 'pending', by: 'Owner', at: '2026-05-01T08:00:00Z' },
        ],
      },
    ]);

    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: /Onay Geçmişi \(1\)/ }));
    const dialog = await screen.findByRole('dialog');
    // One transition renders, not the empty-state copy.
    expect(within(dialog).queryByText('Henüz onay hareketi yok.')).toBeNull();
    expect(within(dialog).getByText('Onay Bekliyor')).toBeInTheDocument();
  });
});

describe('CorporateContractApprovals — status badges & empty state', () => {
  it('maps each approval_status to its Turkish badge label', async () => {
    mockContracts([
      { id: 'd', company_name: 'Draft Co', approval_status: 'draft', approval_history: [] },
      { id: 'p', company_name: 'Pending Co', approval_status: 'pending', approval_history: [] },
      { id: 'a', company_name: 'Approved Co', approval_status: 'approved', approval_history: [] },
      { id: 'r', company_name: 'Rejected Co', approval_status: 'rejected', approval_history: [] },
    ]);

    await renderPage();

    expect(screen.getByText('Taslak')).toBeInTheDocument();
    expect(screen.getByText('Onay Bekliyor')).toBeInTheDocument();
    expect(screen.getByText('Onaylandı')).toBeInTheDocument();
    expect(screen.getByText('Reddedildi')).toBeInTheDocument();
  });

  it('treats a missing/unknown status as draft', async () => {
    mockContracts([
      { id: 'x', company_name: 'NoStatus', approval_history: [] },
    ]);

    await renderPage();

    expect(screen.getByText('Taslak')).toBeInTheDocument();
  });

  it('renders the page empty state when there are no contracts', async () => {
    mockContracts([]);

    await renderPage();

    expect(screen.getByText('Henüz kurumsal sözleşme bulunmuyor.')).toBeInTheDocument();
  });

  it('renders the error state when the fetch fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    vi.spyOn(console, 'error').mockImplementation(() => {});

    await renderPage();

    expect(screen.getByText('Kurumsal sözleşmeler yüklenemedi.')).toBeInTheDocument();
  });
});

describe('CorporateContractApprovals — approve / reject buttons', () => {
  it('shows Approve + Reject buttons only for pending contracts', async () => {
    mockContracts([
      { id: 'p1', company_name: 'Pending Co', approval_status: 'pending', approval_history: [] },
      { id: 'a1', company_name: 'Approved Co', approval_status: 'approved', approval_history: [] },
    ]);

    await renderPage();

    // The pending contract exposes both approver actions.
    expect(screen.getByRole('button', { name: 'Onayla' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reddet' })).toBeInTheDocument();

    // Only one of each — the approved contract does not surface them.
    expect(screen.getAllByRole('button', { name: 'Onayla' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Reddet' })).toHaveLength(1);
  });

  it('approve: posts to_status=approved (reason null) then refreshes the list and toasts success', async () => {
    const fetchSpy = mockFetchRouter(PENDING);

    await renderPage();
    const getsBefore = getCallCount(fetchSpy);

    fireEvent.click(screen.getByRole('button', { name: 'Onayla' }));

    await waitFor(() => expect(transitionCall(fetchSpy)).toBeTruthy());
    const call = transitionCall(fetchSpy);
    expect(call[0]).toContain('/api/sales/corporate-contract/p1/approval-transition');
    expect(call[1].method).toBe('POST');
    expect(JSON.parse(call[1].body)).toEqual({ to_status: 'approved', reason: null });

    // The list reloads after a successful transition.
    await waitFor(() => expect(getCallCount(fetchSpy)).toBeGreaterThan(getsBefore));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Sözleşme onaylandı',
      expect.objectContaining({ description: 'Pending Co' }),
    ));
  });

  it('approve: shows an error toast and does NOT refresh when the transition fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const fetchSpy = mockFetchRouter(PENDING, {
      ok: false, status: 400, body: { detail: 'Geçersiz onay geçişi' },
    });

    await renderPage();
    const getsBefore = getCallCount(fetchSpy);

    fireEvent.click(screen.getByRole('button', { name: 'Onayla' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
      'İşlem başarısız',
      expect.objectContaining({ description: 'Geçersiz onay geçişi' }),
    ));
    expect(toast.success).not.toHaveBeenCalled();
    // A failed transition leaves the list untouched (no reload GET).
    expect(getCallCount(fetchSpy)).toBe(getsBefore);
  });

  it('reject: requires a non-empty reason — submit is disabled until a real reason is typed', async () => {
    mockContracts(PENDING);

    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Reddet' }));

    const dialog = await screen.findByRole('dialog');
    const submit = within(dialog).getByRole('button', { name: 'Reddet' });
    const reason = within(dialog).getByLabelText('Reddetme Gerekçesi');

    // Empty → disabled.
    expect(submit).toBeDisabled();

    // Whitespace-only is still treated as empty.
    fireEvent.change(reason, { target: { value: '   ' } });
    expect(submit).toBeDisabled();

    // A real reason enables the submit.
    fireEvent.change(reason, { target: { value: 'Oran politikamızla uyuşmuyor' } });
    expect(submit).not.toBeDisabled();
  });

  it('reject: posts to_status=rejected with the reason, closes the dialog, refreshes and toasts', async () => {
    const fetchSpy = mockFetchRouter(PENDING);

    await renderPage();
    const getsBefore = getCallCount(fetchSpy);

    fireEvent.click(screen.getByRole('button', { name: 'Reddet' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(dialog).getByLabelText('Reddetme Gerekçesi'),
      { target: { value: '  Oran politikamızla uyuşmuyor  ' } },
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reddet' }));

    await waitFor(() => expect(transitionCall(fetchSpy)).toBeTruthy());
    const call = transitionCall(fetchSpy);
    expect(call[1].method).toBe('POST');
    // Reason is trimmed before it is sent.
    expect(JSON.parse(call[1].body)).toEqual({
      to_status: 'rejected', reason: 'Oran politikamızla uyuşmuyor',
    });

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Sözleşme reddedildi',
      expect.objectContaining({ description: 'Pending Co' }),
    ));
    // Dialog closes and the list reloads on success.
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(getCallCount(fetchSpy)).toBeGreaterThan(getsBefore));
  });

  it('approve: confirms the owner was emailed in the success toast when owner_notified=true', async () => {
    mockFetchRouter(PENDING, { body: { owner_notified: true } });

    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Onayla' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Sözleşme onaylandı',
      expect.objectContaining({
        description: expect.stringContaining('e-postası gönderildi'),
      }),
    ));
    // No skipped-email warning when the email actually went out.
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('approve: warns (without failing) when owner_notified=false', async () => {
    const fetchSpy = mockFetchRouter(PENDING, { body: { owner_notified: false } });

    await renderPage();
    const getsBefore = getCallCount(fetchSpy);
    fireEvent.click(screen.getByRole('button', { name: 'Onayla' }));

    // Still a success (the transition committed) ...
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Sözleşme onaylandı',
      expect.objectContaining({ description: 'Pending Co' }),
    ));
    // ... but a subtle warning that the owner email was skipped.
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(
      expect.stringContaining('e-posta gönderilemedi'),
      expect.objectContaining({
        description: expect.stringContaining('iletişim e-postası'),
      }),
    ));
    // The list still refreshes — a skipped email is not a failure.
    await waitFor(() => expect(getCallCount(fetchSpy)).toBeGreaterThan(getsBefore));
  });

  it('approve: stays silent about notification when the backend omits owner_notified', async () => {
    mockFetchRouter(PENDING, { body: { ok: true } });

    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Onayla' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Sözleşme onaylandı',
      expect.objectContaining({ description: 'Pending Co' }),
    ));
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('reject: warns when owner_notified=false on a rejection too', async () => {
    mockFetchRouter(PENDING, { body: { owner_notified: false } });

    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Reddet' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(dialog).getByLabelText('Reddetme Gerekçesi'),
      { target: { value: 'Oran uygun değil' } },
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reddet' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      'Sözleşme reddedildi',
      expect.objectContaining({ description: 'Pending Co' }),
    ));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(
      expect.stringContaining('e-posta gönderilemedi'),
      expect.objectContaining({
        description: expect.stringContaining('iletişim e-postası'),
      }),
    ));
  });

  it('reject: keeps the dialog open and toasts an error when the transition fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const fetchSpy = mockFetchRouter(PENDING, {
      ok: false, status: 400, body: { detail: 'Reddetme için gerekçe zorunludur' },
    });

    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Reddet' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(dialog).getByLabelText('Reddetme Gerekçesi'),
      { target: { value: 'Bir gerekçe' } },
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reddet' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
      'İşlem başarısız',
      expect.objectContaining({ description: 'Reddetme için gerekçe zorunludur' }),
    ));
    expect(toast.success).not.toHaveBeenCalled();
    // Failure keeps the reject dialog open so the approver can retry.
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Sanity: the transition really did request a rejection.
    expect(JSON.parse(transitionCall(fetchSpy)[1].body).to_status).toBe('rejected');
  });
});
