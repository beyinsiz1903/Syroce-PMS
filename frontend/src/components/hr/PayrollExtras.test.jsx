import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import PayrollExtras from './PayrollExtras';

vi.mock('axios', () => ({ default: { put: vi.fn() } }));
const run = { id: 'qa', updated_at: 'v1', status: 'draft', rows: [{ staff_id: 'staff', staff_name: 'QA' }], extras: [], summary: { total_employer_contributions: 12587.5, total_employer_cost: 65587.5 } };
beforeEach(() => vi.clearAllMocks());

describe('Payroll extra lines', () => {
  it('submits prim and advance with the draft version and recomputes', async () => {
    axios.put.mockResolvedValue({ data: { success: true } });
    const saved = vi.fn().mockResolvedValue(); const dirty = vi.fn();
    render(<PayrollExtras run={run} onSaved={saved} onDirty={dirty} />);
    for (const [index, kind, amount] of [[1, 'bonus', '2000'], [2, 'advance', '500']]) {
      fireEvent.click(screen.getByText('Kalem Ekle'));
      fireEvent.change(screen.getByLabelText(`Kalem ${index} personel`), { target: { value: 'staff' } });
      fireEvent.change(screen.getByLabelText(`Kalem ${index} tür`), { target: { value: kind } });
      fireEvent.change(screen.getByLabelText(`Kalem ${index} tutar`), { target: { value: amount } });
      fireEvent.change(screen.getByLabelText(`Kalem ${index} açıklama`), { target: { value: 'QA belge' } });
    }
    fireEvent.click(screen.getByText('Kalemleri Kaydet ve Yeniden Hesapla'));
    await waitFor(() => expect(saved).toHaveBeenCalledWith('qa'));
    expect(axios.put).toHaveBeenCalledWith('/hr/payroll/runs/qa/extras', { expected_updated_at: 'v1', extras: [
      { staff_id: 'staff', kind: 'bonus', amount: 2000, note: 'QA belge' },
      { staff_id: 'staff', kind: 'advance', amount: 500, note: 'QA belge' },
    ] });
    expect(dirty).toHaveBeenCalledWith(false);
  });

  it('preserves existing lines and persists explicit removal', async () => {
    axios.put.mockResolvedValue({});
    render(<PayrollExtras run={{ ...run, extras: [{ staff_id: 'staff', kind: 'advance', amount: 500, note: 'existing' }] }} onSaved={vi.fn()} />);
    expect(screen.getByLabelText('Kalem 1 tutar').value).toBe('500');
    fireEvent.click(screen.getByText('Kalem 1 sil'));
    fireEvent.click(screen.getByText('Kalemleri Kaydet ve Yeniden Hesapla'));
    await waitFor(() => expect(axios.put).toHaveBeenCalledWith('/hr/payroll/runs/qa/extras', { expected_updated_at: 'v1', extras: [] }));
  });

  it('does not allow changing locked snapshots', () => {
    render(<PayrollExtras run={{ ...run, status: 'locked' }} onSaved={vi.fn()} />);
    expect(screen.queryByText('Kalem Ekle')).toBeNull();
    expect(screen.queryByText('Kalemleri Kaydet ve Yeniden Hesapla')).toBeNull();
    expect(axios.put).not.toHaveBeenCalled();
  });

  it('keeps inputs after a stale version conflict and shows the server error', async () => {
    axios.put.mockRejectedValue({ response: { data: { detail: 'Bordro başka bir oturumda değişti' } } });
    const saved = vi.fn();
    render(<PayrollExtras run={run} onSaved={saved} />);
    fireEvent.click(screen.getByText('Kalemleri Kaydet ve Yeniden Hesapla'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Bordro başka bir oturumda değişti');
    expect(saved).not.toHaveBeenCalled();
  });
});
