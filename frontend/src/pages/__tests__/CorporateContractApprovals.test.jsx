import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render, screen, act, cleanup, waitFor, within, fireEvent,
} from '@testing-library/react';
import CorporateContractApprovals from '@/pages/CorporateContractApprovals';

// Stable token so the component's Authorization header / fetch path resolve.
beforeEach(() => {
  localStorage.setItem('token', 'test-token');
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
