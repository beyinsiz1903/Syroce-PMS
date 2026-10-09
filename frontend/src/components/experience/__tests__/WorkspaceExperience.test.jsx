import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import tr from '@/locales/tr.json';
import GuestContextPanel from '../GuestContextPanel';
import WorkInbox from '../WorkInbox';
import WorkspaceTools from '../WorkspaceTools';
import ReservationPicker from '../ReservationPicker';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => key.split('.').reduce((o, k) => o?.[k], tr) || (typeof fallback === 'string' ? fallback : fallback?.defaultValue) || key }) }));

describe('workspace experience', () => {
  beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); localStorage.clear(); });
  it('does not fetch guest information before an explicit search', () => {
    render(<GuestContextPanel open scope="u:h" onOpenChange={() => {}} />);
    expect(axios.get).not.toHaveBeenCalled();
    expect(screen.getByText('Aramak için en az iki karakter yazın.')).toBeInTheDocument();
  });
  it('opens a profile without changing routes or storing guest data', async () => {
    axios.get.mockResolvedValueOnce({ data: [{ id: 'g1', name: 'Example Guest' }] })
      .mockResolvedValueOnce({ data: { guest: { name: 'Example Guest', email: 'private@example.test' }, stay_history: [] } });
    render(<GuestContextPanel open scope="u:h" onOpenChange={() => {}} />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Misafir ara' }), { target: { value: 'Example' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Example Guest' }));
    expect(await screen.findByText('private@example.test')).toBeInTheDocument();
    expect(axios.get.mock.calls[1][0]).toBe('/crm/guest/g1');
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
  });
  it('does not render an obsolete guest response after a new selection', async () => {
    let resolveOld;
    axios.get.mockImplementation(url => url.endsWith('/old') ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve({ data: { guest: { name: 'Current Guest' } } }));
    const { rerender } = render(<GuestContextPanel open guestId="old" scope="u:h" onOpenChange={() => {}} />);
    await waitFor(() => expect(resolveOld).toBeTypeOf('function'));
    rerender(<GuestContextPanel open guestId="new" scope="u:h" onOpenChange={() => {}} />);
    expect(await screen.findByText('Current Guest')).toBeInTheDocument();
    await act(async () => resolveOld({ data: { guest: { name: 'Obsolete Guest' } } }));
    expect(screen.queryByText('Obsolete Guest')).not.toBeInTheDocument();
  });
  it('loads only authorized work sources and distinguishes partial failures', async () => {
    axios.get.mockImplementation(url => url.includes('staff-tasks') ? Promise.resolve({ data: { tasks: [{ id: '1', title: 'Repair lamp', status: 'pending' }], total: 250 } }) : Promise.reject(new Error('offline')));
    render(<MemoryRouter><WorkInbox scope="u:h" items={[{ key: 'tasks_workspace', path: '/app/tasks' }, { key: 'shift_handover', path: '/shift-handover' }]} /></MemoryRouter>);
    expect(await screen.findByText('Repair lamp')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('liste eksik olabilir');
    expect(screen.getByText(/Bu liste bir önizlemedir/)).toBeInTheDocument();
    expect(axios.get.mock.calls.some(([url]) => url.includes('operational-alerts'))).toBe(false);
  });
  it('closes the work panel before navigating to a source', async () => {
    const onOpenSource = vi.fn();
    axios.get.mockResolvedValue({ data: { tasks: [{ id: '1', title: 'Repair lamp', status: 'pending' }], total: 1 } });
    render(<MemoryRouter><WorkInbox scope="u:h" onOpenSource={onOpenSource} items={[{ key: 'tasks_workspace', path: '/app/tasks' }]} /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Kaynak ekranını aç' }));
    expect(onOpenSource).toHaveBeenCalledTimes(1);
  });
  it('clears the inbox when the tenant changes before old responses finish', async () => {
    let finish;
    axios.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve; })).mockResolvedValue({ data: { tasks: [], total: 0 } });
    const items = [{ key: 'tasks_workspace', path: '/app/tasks' }];
    const { rerender } = render(<MemoryRouter><WorkInbox scope="u:h1" items={items} /></MemoryRouter>);
    rerender(<MemoryRouter><WorkInbox scope="u:h2" items={items} /></MemoryRouter>);
    await act(async () => finish({ data: { tasks: [{ id: 'private', title: 'Other hotel', status: 'pending' }] } }));
    expect(screen.queryByText('Other hotel')).not.toBeInTheDocument();
  });
  it('hides guest tools from a scope-restricted user', () => {
    render(<WorkspaceTools user={{ id: 'u', role: 'staff', module_scopes: [] }} tenant={{ id: 'h' }} items={[]} />);
    expect(screen.queryByRole('button', { name: 'Misafir özeti' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'İş takibi' })).not.toBeInTheDocument();
  });
  it('selects a reservation record instead of accepting a manual identifier', async () => {
    const onSelect = vi.fn();
    axios.get.mockResolvedValue({ data: { bookings: [{ id: 'b1', guest_name: 'Example Guest', booking_number: 'R-42', check_in: '2026-10-09', check_out: '2026-10-10' }] } });
    render(<ReservationPicker value="" onSelect={onSelect} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Example' } });
    fireEvent.click(await screen.findByRole('button', { name: /Example Guest/ }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'b1' }));
  });
});
