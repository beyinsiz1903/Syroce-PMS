import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('axios', () => ({ default: api }));
import DataMigrationCutover from '@/pages/DataMigrationCutover';

const token = 'a'.repeat(64);
const config = { cutover_date: '2026-10-21', source_frozen_at: '2026-10-21T18:00:00+03:00', target_links: { rooms: { old: 'new' } }, accounts: {}, exchange_rates: { TRY: '1' }, source_writes_stopped: true };
const reviewed = { state: 'reviewed', config, cursor: 0, review_token: token, report: { bookings: 1, folios: 1, balances: 0, errors: [], error_count: 0, totals: {}, voucher_required: false } };
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ data: reviewed }); });

describe('Explicit live cutover', () => {
  it('does not activate or create vouchers on mount and requires typed confirmation', async () => {
    render(<DataMigrationCutover batchId="b1" />);
    const activate = await screen.findByRole('button', { name: /Onaylı canlı devri/ });
    expect(activate).toBeDisabled(); expect(api.post).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('CANLI DEVRI ONAYLIYORUM yazın'), { target: { value: 'CANLI DEVRI ONAYLIYORUM' } });
    expect(activate).toBeEnabled();
    api.post.mockResolvedValue({ data: { ...reviewed, state: 'complete', cursor: 1 } });
    fireEvent.click(activate);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/data-migration/batches/b1/cutover/activate', { review_token: token, confirmation: 'CANLI DEVRI ONAYLIYORUM' }, expect.any(Object)));
    expect(await screen.findByText(/Canlı devir tamamlandı/)).toBeInTheDocument();
  });

  it('invalidates confirmation for unsaved mapping edits', async () => {
    render(<DataMigrationCutover batchId="b1" />);
    const activate = await screen.findByRole('button', { name: /Onaylı canlı devri/ });
    fireEvent.change(screen.getByLabelText('CANLI DEVRI ONAYLIYORUM yazın'), { target: { value: 'CANLI DEVRI ONAYLIYORUM' } });
    fireEvent.change(screen.getByLabelText('Eski kaynak no → mevcut hedef ID (JSON)'), { target: { value: '{}' } });
    expect(activate).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Canlı devir denemesi ve çakışma kontrolü' })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('cannot bypass a required draft voucher and surfaces server rejection', async () => {
    api.get.mockResolvedValue({ data: { ...reviewed, report: { ...reviewed.report, voucher_required: true } } });
    render(<DataMigrationCutover batchId="b1" />);
    const activate = await screen.findByRole('button', { name: /Onaylı canlı devri/ });
    fireEvent.change(screen.getByLabelText('CANLI DEVRI ONAYLIYORUM yazın'), { target: { value: 'CANLI DEVRI ONAYLIYORUM' } });
    expect(activate).toBeDisabled();
    api.post.mockRejectedValue({ response: { data: { detail: 'Muhasebe kurulumunu tamamlayın.' } } });
    fireEvent.click(screen.getByRole('button', { name: /Açılış fişini taslak/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Muhasebe kurulumunu tamamlayın.');
    expect(api.post.mock.calls.every(([url]) => !url.endsWith('/activate'))).toBe(true);
  });
});
