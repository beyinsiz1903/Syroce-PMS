import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import SpaResidentTarget from '../SpaResidentTarget';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
const booking = (id, currency = 'TRY', status = 'checked_in') => ({ id, currency, status, guest_name: id === 'b1' ? 'Selin Kaya' : 'Deniz Tan', room_number: id === 'b1' ? '101' : '102', check_in: '2026-11-10', check_out: '2026-11-12' });
const folio = (id, bookingId = 'b1', extra = {}) => ({ id, booking_id: bookingId, currency: 'TRY', status: 'open', folio_number: id, ...extra });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
beforeEach(() => vi.resetAllMocks());
async function choose(id = 'b1') { await screen.findByRole('option', { name: /Selin Kaya/ }); fireEvent.change(screen.getByLabelText('Konaklayan misafir'), { target: { value: id } }); }

describe('SPA resident account selection', () => {
  it('shows names and room numbers and excludes departures and other currencies', async () => {
    axios.get.mockResolvedValue({ data: [booking('b1'), booking('usd', 'USD'), booking('left', 'TRY', 'checked_out')] });
    render(<SpaResidentTarget currency="TRY" onTargetChange={vi.fn()} />);
    expect(await screen.findByRole('option', { name: /Selin Kaya · Oda 101/ })).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(screen.queryByPlaceholderText(/ID/)).not.toBeInTheDocument();
  });
  it('automatically resolves exactly one eligible account and never chooses a foreign/invoiced/closed account', async () => {
    const changed = vi.fn();
    axios.get.mockResolvedValueOnce({ data: [booking('b1')] }).mockResolvedValueOnce({ data: [folio('open'), folio('closed', 'b1', { status: 'closed' }), folio('invoice', 'b1', { invoice_id: 'inv' }), folio('foreign', 'other'), folio('fx', 'b1', { currency: 'USD' })] });
    render(<SpaResidentTarget currency="TRY" onTargetChange={changed} />); await choose();
    await waitFor(() => expect(changed).toHaveBeenLastCalledWith({ reservation_id: 'b1', folio_id: 'open', guest_name: 'Selin Kaya' }));
    expect(screen.getByLabelText('Masrafın yazılacağı hesap')).toHaveValue('open');
  });
  it('requires an explicit choice with multiple open accounts', async () => {
    const changed = vi.fn();
    axios.get.mockResolvedValueOnce({ data: [booking('b1')] }).mockResolvedValueOnce({ data: { folios: [folio('guest'), folio('company', 'b1', { folio_type: 'company' })] } });
    render(<SpaResidentTarget currency="TRY" onTargetChange={changed} />); await choose();
    await screen.findByRole('option', { name: /company · Şirket/ });
    expect(changed).toHaveBeenLastCalledWith(null);
    fireEvent.change(screen.getByLabelText('Masrafın yazılacağı hesap'), { target: { value: 'company' } });
    expect(changed).toHaveBeenLastCalledWith({ reservation_id: 'b1', folio_id: 'company', guest_name: 'Selin Kaya' });
  });
  it('ignores a delayed account response after switching guests', async () => {
    const old = deferred(); const changed = vi.fn();
    axios.get.mockImplementation(url => url === '/frontdesk/inhouse' ? Promise.resolve({ data: [booking('b1'), booking('b2')] }) : url.endsWith('b1') ? old.promise : Promise.resolve({ data: [folio('f2', 'b2')] }));
    render(<SpaResidentTarget currency="TRY" onTargetChange={changed} />); await choose();
    fireEvent.change(screen.getByLabelText('Konaklayan misafir'), { target: { value: 'b2' } });
    await waitFor(() => expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ reservation_id: 'b2', folio_id: 'f2' })));
    await act(async () => old.resolve({ data: [folio('old')] }));
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ reservation_id: 'b2', folio_id: 'f2' }));
  });
  it('clears the target when service currency changes', async () => {
    const changed = vi.fn(); axios.get.mockResolvedValueOnce({ data: [booking('b1')] }).mockResolvedValueOnce({ data: [folio('f1')] });
    const view = render(<SpaResidentTarget currency="TRY" onTargetChange={changed} />); await choose();
    await waitFor(() => expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ folio_id: 'f1' })));
    view.rerender(<SpaResidentTarget currency="USD" onTargetChange={changed} />);
    await waitFor(() => expect(changed).toHaveBeenLastCalledWith(null));
    expect(screen.queryByRole('option', { name: /f1/ })).not.toBeInTheDocument();
  });
  it('fails closed on a malformed or failed account read and offers retry', async () => {
    const changed = vi.fn(); axios.get.mockResolvedValueOnce({ data: [booking('b1')] }).mockResolvedValueOnce({ data: {} });
    render(<SpaResidentTarget currency="TRY" onTargetChange={changed} />); await choose();
    expect(await screen.findByRole('alert')).toHaveTextContent('açık hesapları yüklenemedi');
    expect(changed).toHaveBeenLastCalledWith(null);
    expect(screen.getByRole('button', { name: 'Yenile' })).toBeInTheDocument();
  });
});
