import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const axiosPost = vi.fn();
const mockEntitlements = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: (...args) => axiosPost(...args),
  },
}));

vi.mock('@/context/EntitlementContext', () => ({
  useEntitlements: () => mockEntitlements(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import MicePage, { canDeleteMiceEvent, omitEmptySpaceBookings } from '@/pages/MicePage';

describe('MicePage event payload normalization', () => {
  it.each([
    { status: 'completed' }, { status: 'unknown' }, { status: 'lead', folio_charge_id: 'charge' },
    { status: 'confirmed', settlement_count: 1 }, { status: 'definite', finance_pending: { payment_id: 'pending' } },
    { status: 'cancelled', signature: { id: 'signed' } }, { status: 'lead', gl_posting_state: 'pending' },
    { status: 'lead', document_history: [{ id: 'frozen' }] }, { status: 'confirmed', group_block_id: 'group' },
    { status: 'confirmed', sales_opportunity_id: 'opportunity' }, { status: 'lead', operations_tasks: [{ id: 'task' }] },
    { status: 'confirmed', last_kitchen_dispatch_at: '2026-11-08' }, { status: 'lead', payment_schedule: [{ paid: true }] },
  ])('preserves terminal, financial and operational source history: %j', event => {
    expect(canDeleteMiceEvent(event)).toBe(false);
  });

  it.each(['lead', 'tentative', 'definite', 'confirmed', 'cancelled'])('allows a clean unposted %s draft', status => {
    expect(canDeleteMiceEvent({ status, settlement_count: 0, payment_schedule: [{ paid: false }] })).toBe(true);
  });

  it('omits the untouched convenience space row', () => {
    expect(omitEmptySpaceBookings([
      {
        space_id: '',
        starts_at: '',
        ends_at: '',
        setup_style: 'theatre',
        expected_pax: 50,
      },
    ])).toEqual([]);
  });

  it('keeps configured and partially configured rows for server validation', () => {
    const configured = {
      space_id: 'space-1',
      starts_at: '2026-08-20T10:00',
      ends_at: '2026-08-20T12:00',
    };
    const partial = { space_id: 'space-2', starts_at: '', ends_at: '' };

    expect(omitEmptySpaceBookings([configured, partial])).toEqual([configured, partial]);
  });
});

describe('MicePage entitlement usage contract', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPost.mockReset();
    mockEntitlements.mockReset();
    mockEntitlements.mockReturnValue({
      entitlements: {
        mice: {
          features: [],
          limits: { spaces_limit: 10, concurrent_events: 50 },
          usage: { spaces_limit: 2, concurrent_events: 3 },
        },
      },
    });
    axiosGet.mockImplementation((url) => {
      if (url === '/mice/events') {
        return Promise.resolve({ data: { events: [], summary: {}, counts: {} } });
      }
      if (url === '/mice/spaces') {
        return Promise.resolve({ data: { spaces: [] } });
      }
      if (url === '/mice/accounts') {
        return Promise.resolve({ data: { accounts: [] } });
      }
      return Promise.reject(new Error(`Unexpected GET: ${url}`));
    });
  });

  it('renders after loading quota usage from the entitlement payload', async () => {
    render(
      <MemoryRouter>
        <MicePage user={{ role: 'admin' }} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'MICE & Banquet' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /yeni_etkinlik/ })).toBeEnabled();
    expect(axiosGet).toHaveBeenCalledWith('/mice/events');
    expect(axiosGet).toHaveBeenCalledWith('/mice/spaces');
    expect(axiosGet).toHaveBeenCalledWith('/mice/accounts');
  });

  it('updates an already visited diary without clearing its selected day when a hall hold is created', async () => {
    const now = new Date();
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-11`;
    const space = { id: 'boardroom', name: 'Boardroom' };
    let event = {
      id: 'atelier', name: 'Anadolu Hizmet Atölyesi', client_name: 'Zeynep Aksoy', status: 'lead',
      start_date: date, end_date: date, currency: 'TRY', expected_pax: 4,
      space_bookings: [{ space_id: space.id, starts_at: `${date}T10:00`, ends_at: `${date}T11:00` }],
    };
    axiosGet.mockImplementation(async (url) => {
      if (url === '/mice/events') return { data: { events: [event] } };
      if (url === '/mice/diary') return { data: { events: event.status === 'lead' ? [] : [event] } };
      if (url === '/mice/spaces') return { data: { spaces: [space] } };
      if (url === '/mice/accounts') return { data: { accounts: [] } };
      throw new Error(`Unexpected GET: ${url}`);
    });
    axiosPost.mockImplementation(async () => {
      event = { ...event, status: 'tentative' };
      return { data: event };
    });
    render(<MemoryRouter><MicePage user={{ role: 'admin' }} tenant={{}} onLogout={vi.fn()} /></MemoryRouter>);

    const diary = await screen.findByRole('tab', { name: 'Function Diary' });
    fireEvent.mouseDown(diary, { button: 0 });
    fireEvent.click(await screen.findByRole('button', { name: /^11 1\/1/ }));
    expect(within(screen.getByRole('tabpanel', { name: 'Function Diary' })).getByText(date)).toBeVisible();

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Etkinlikler' }), { button: 0 });
    fireEvent.change(screen.getByRole('combobox', { name: /Anadolu Hizmet Atölyesi durum değiştir/ }), { target: { value: 'tentative' } });
    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/mice/events/atelier/status', { status: 'tentative' }));
    fireEvent.mouseDown(diary, { button: 0 });
    const panel = screen.getByRole('tabpanel', { name: 'Function Diary' });
    expect(await within(panel).findByRole('button', { name: /^11 1 0\/1/ })).toBeVisible();
    expect(within(panel).getByText(date)).toBeVisible();
    expect(within(panel).getByText('Anadolu Hizmet Atölyesi')).toBeVisible();
  });

  it('does not offer deletion for completed source history', async () => {
    axiosGet.mockImplementation(url => Promise.resolve({ data: url === '/mice/events'
      ? { events: [{ id: 'completed', name: 'Finished event', status: 'completed', client_name: 'Synthetic client', totals: { grand_total: 100 } }], summary: {}, counts: {} }
      : url === '/mice/spaces' ? { spaces: [] } : { accounts: [] } }));
    render(<MemoryRouter><MicePage user={{ role: 'admin' }} tenant={{}} onLogout={vi.fn()} /></MemoryRouter>);
    const row = (await screen.findByText('Finished event')).closest('tr');
    expect(within(row).queryByRole('button', { name: '' })).not.toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Finished event sil' })).not.toBeInTheDocument();
  });

  it('keeps a rejected salon booking open and shows its conflict inside the form', async () => {
    axiosPost.mockRejectedValue({ response: { status: 409, data: { detail: 'Mekan çakışması: Anadolu Hizmet Atölyesi' } } });
    render(<MemoryRouter><MicePage user={{ role: 'admin' }} tenant={{}} onLogout={vi.fn()} /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /yeni_etkinlik/ }));
    const dialog = screen.getByRole('dialog', { name: 'Yeni Etkinlik' });
    expect(within(dialog).getByText('Başlangıç tarihi seçilmedi.')).toBeVisible();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Oluştur' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent('başlangıç ile bitiş tarihlerini tamamlayın');
    expect(axiosPost).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText('Etkinlik Adı'), { target: { value: 'Salon Çakışma Kontrolü' } });
    fireEvent.change(within(dialog).getByLabelText('Müşteri Adı'), { target: { value: 'Deren Özkan' } });
    for (const dateInput of dialog.querySelectorAll('input[type="date"]')) {
      fireEvent.change(dateInput, { target: { value: '2026-11-11' } });
    }
    fireEvent.click(within(dialog).getByRole('button', { name: 'Oluştur' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Mekan çakışması: Anadolu Hizmet Atölyesi');
    expect(within(dialog).getByLabelText('Etkinlik Adı')).toHaveValue('Salon Çakışma Kontrolü');
  });

  it('keeps the new event action disabled when entitlement usage reaches the limit', async () => {
    mockEntitlements.mockReturnValue({
      entitlements: {
        mice: {
          features: [],
          limits: { spaces_limit: 10, concurrent_events: 5 },
          usage: { spaces_limit: 2, concurrent_events: 5 },
        },
      },
    });

    render(
      <MemoryRouter>
        <MicePage user={{ role: 'admin' }} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'MICE & Banquet' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /yeni_etkinlik/ })).toBeDisabled();
  });

  it('fails closed without crashing when the feature payload is malformed', async () => {
    mockEntitlements.mockReturnValue({
      entitlements: {
        mice: {
          features: { banquet_operations: true },
          limits: { spaces_limit: 10, concurrent_events: 50 },
          usage: { spaces_limit: 2, concurrent_events: 3 },
        },
      },
    });

    render(
      <MemoryRouter>
        <MicePage user={{ role: 'admin' }} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: 'MICE & Banquet' })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /gunun_ops_sheet_i/ })).not.toBeInTheDocument();
  });
});
