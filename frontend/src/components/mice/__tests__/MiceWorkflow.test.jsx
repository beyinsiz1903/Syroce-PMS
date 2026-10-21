import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import SpacesView from '../SpacesView';
import { bookedSpacesOnDate } from '../DiaryView';
import { eventReadiness } from '../ReadinessPanel';
import PublicMiceBeoPage from '@/pages/PublicMiceBeoPage';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));

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
