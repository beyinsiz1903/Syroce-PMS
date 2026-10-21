import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import SpacesView from '../SpacesView';
import { bookedSpacesOnDate } from '../DiaryView';
import { eventReadiness } from '../ReadinessPanel';
import PublicMiceBeoPage from '@/pages/PublicMiceBeoPage';
import QuoteTotals from '../QuoteTotals';
import EventCommercialPanel from '../EventCommercialPanel';
import OperationTasks from '../OperationTasks';
import FnbSnapshot from '../FnbSnapshot';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true), promptDialog: vi.fn().mockResolvedValue('Test belge sürümü') }));

beforeEach(() => { vi.clearAllMocks(); });

describe('MICE catalog workflows', () => {
  it('creates a real venue through the same catalog used by event bookings', async () => {
    axios.post.mockResolvedValue({ data: { id: 'hall-new' } });
    const reload = vi.fn().mockResolvedValue();
    render(<SpacesView spaces={[]} canManage reload={reload} />);
    fireEvent.click(screen.getByRole('button', { name: 'Yeni Mekan' }));
    fireEvent.change(screen.getByLabelText('Mekan adı'), { target: { value: 'Kongre Salonu' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/mice/spaces', expect.objectContaining({ name: 'Kongre Salonu' })));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it('opens and saves the existing venue without losing amenities', async () => {
    axios.put.mockResolvedValue({ data: { ok: true } });
    render(<SpacesView spaces={[{ id: 'hall-1', name: 'Balo', amenities: ['wifi'], hourly_rate: 100, daily_rate: 500, currency: 'TRY' }]} canManage reload={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Balo düzenle' }));
    fireEvent.change(screen.getByLabelText('Mekan adı'), { target: { value: 'Yeni Balo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
    await waitFor(() => expect(axios.put).toHaveBeenCalledWith('/mice/spaces/hall-1', expect.objectContaining({ name: 'Yeni Balo', amenities: ['wifi'] })));
  });

  it('does not offer catalog mutations to a read-only user', () => {
    render(<SpacesView spaces={[]} canManage={false} reload={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Yeni Mekan' })).not.toBeInTheDocument();
  });
});

describe('Function diary availability', () => {
  const span = (from, to) => ({ space_id: 'hall-1', starts_at: `2026-10-${from}T10:00`, ends_at: `2026-10-${to}T12:00` });
  it('does not count a cancelled event or a sales lead as an occupied venue', () => {
    expect(bookedSpacesOnDate([{ status: 'cancelled', space_bookings: [span('21', '21')] }, { status: 'lead', space_bookings: [span('21', '21')] }], '2026-10-21').size).toBe(0);
  });
  it('uses the actual function day, not the envelope of a multi-day event', () => {
    const events = [{ status: 'confirmed', space_bookings: [span('21', '21')] }];
    expect(bookedSpacesOnDate(events, '2026-10-21').has('hall-1')).toBe(true);
    expect(bookedSpacesOnDate(events, '2026-10-22').size).toBe(0);
  });
  it('ignores terminal events in the readiness list', () => {
    expect(eventReadiness({ status: 'cancelled' }, '2026-10-21')).toEqual([]);
    expect(eventReadiness({ status: 'lead', totals: { grand_total: 100 } }, '2026-10-21')).toContain('Ödeme planı eksik');
  });
  it('includes the setup time on the preceding calendar day', () => {
    const events = [{ status: 'confirmed', space_bookings: [{ space_id: 'hall', starts_at: '2026-10-21T00:15', ends_at: '2026-10-21T01:00', setup_minutes: 60 }] }];
    expect(bookedSpacesOnDate(events, '2026-10-20').has('hall')).toBe(true);
  });
});

describe('Departmental operations', () => {
  it('records a department task through its scoped API without changing revenue', async () => {
    axios.get.mockResolvedValue({ data: { tasks: [], equipment: [], event_status: 'definite' } });
    axios.post.mockResolvedValue({ data: { id: 'task' } });
    render(<OperationTasks eventId="event" canManage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Yeni görev / teslim planı' }));
    fireEvent.change(screen.getByLabelText('Görev başlığı'), { target: { value: 'Sahneyi hazırla' } });
    fireEvent.change(screen.getByLabelText('Sorumlu kişi'), { target: { value: 'Yapay teknisyen' } });
    fireEvent.click(screen.getByRole('button', { name: 'Görevi kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/mice/events/event/tasks', expect.objectContaining({ title: 'Sahneyi hazırla', owner_name: 'Yapay teknisyen', client_request_id: expect.any(String) })));
    expect(axios.post.mock.calls.every(([url]) => !url.includes('payment'))).toBe(true);
  });
  it('shows the frozen meal and allergens with a revision warning', () => {
    render(<FnbSnapshot order={{ needs_review: true, lines: [{ name: 'Örnek menü', quantity: 20, unit: 'pax', menu_snapshot: { allergens: ['milk'], dietary_tags: ['vegetarian'], courses: [{ name: 'Çorba' }] } }] }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('teyit edin');
    expect(screen.getByText('Alerjenler: milk')).toBeInTheDocument();
    expect(screen.getByText('1. Çorba')).toBeInTheDocument();
  });
});

describe('Public BEO approval', () => {
  it('fails closed without a private token', async () => {
    render(<MemoryRouter><PublicMiceBeoPage /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('bağlantısı eksik');
    expect(axios.get).not.toHaveBeenCalled();
  });
  it('requires explicit client consent and shows the real server currency', async () => {
    axios.get.mockResolvedValue({ data: { event: { name: 'Congress', status: 'definite', client_name: 'Example', currency: 'EUR', totals: { grand_total: 100 } }, spaces: [], resources: [], payment_schedule: [] } });
    axios.post.mockResolvedValue({ data: { success: true } });
    render(<MemoryRouter initialEntries={['/public/mice/beo?token=private-test-token']}><PublicMiceBeoPage /></MemoryRouter>);
    const action = await screen.findByRole('button', { name: 'Etkinliği onayla' });
    expect(action).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Onaylayan ad soyad'), { target: { value: 'Test Müşteri' } });
    fireEvent.click(screen.getByRole('checkbox'));
    expect(action).toBeEnabled();
    fireEvent.click(action);
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/mice/public/beo/sign', expect.objectContaining({ token: 'private-test-token', signature_name: 'Test Müşteri' })));
    expect(await screen.findByText(/Müşteri onayı kaydedildi/)).toBeInTheDocument();
  });
});

describe('Versioned commercial workflows', () => {
  it('shows the server-owned discount service and tax without recalculating them', () => {
    render(<QuoteTotals totals={{ subtotal: 100, discount_total: 10, net_total: 90, service_total: 9, tax_total: 19.8, grand_total: 118.8 }} currency="EUR" />);
    expect(screen.getByText('İndirim (−)')).toBeInTheDocument();
    expect(screen.getByText('Servis (+)')).toBeInTheDocument();
    expect(screen.getByText('Vergi (+)')).toBeInTheDocument();
    expect(screen.getByText('Ödenecek toplam').nextSibling).toHaveTextContent('118,80');
  });
  it('issues a version with concurrency revision and a replay key', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/documents') ? { documents: [] } : { id: 'event', status: 'definite', updated_at: 'revision-a' } }));
    axios.post.mockResolvedValue({ data: { number: 1 } });
    render(<EventCommercialPanel eventId="event" canManage />);
    fireEvent.click(await screen.findByRole('button', { name: 'BEO sürümü kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/mice/events/event/documents', expect.objectContaining({ reason: 'Test belge sürümü', expected_revision: 'revision-a', client_request_id: expect.any(String) })));
  });
  it('does not expose costs or financial controls to an operations reader', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/documents') ? { documents: [] } : { id: 'event', status: 'definite' } }));
    render(<EventCommercialPanel eventId="event" canManage={false} canFinance={false} />);
    await screen.findByText('Henüz kayıtlı belge sürümü yok.');
    expect(screen.queryByRole('button', { name: 'Katılım / maliyet analizi' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'BEO sürümü kaydet' })).not.toBeInTheDocument();
    expect(axios.get).not.toHaveBeenCalledWith('/mice/events/event/actuals');
  });
});
