import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import SalaryAgreementFields, { newSalaryAgreement } from './SalaryAgreementFields';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));
const complete = () => ({ ...newSalaryAgreement(), amount: '33030', period_month: '2026-01',
  opening_tax_base: '0', opening_exemption_base: '0', paid_hours: '225',
  standard_4a_confirmed: true, source_note: 'QA bordro' });
function Form({ initial = null }) {
  const [value, setValue] = useState(initial);
  return <SalaryAgreementFields value={value} onChange={setValue} />;
}
const result = { gross_pay: 33030, net_salary: 28075.5, sgk_employee: 4624.2,
  unemployment: 330.3, income_tax: 0, stamp_tax: 0, tax_calculation: { closing_tax_base: 28075.5 } };
describe('Salary agreements', () => {
  beforeEach(() => { axios.post.mockReset(); axios.post.mockResolvedValue({ data: result }); });
  afterEach(() => { vi.restoreAllMocks(); });
  it('offers monthly/hourly and net/gross without assuming tax history', () => {
    render(<Form />);
    fireEvent.click(screen.getByRole('button', { name: /anlaşması tanımla/ }));
    expect(screen.getByLabelText('Ücret dönemi')).toHaveValue('monthly');
    fireEvent.change(screen.getByLabelText('Ücret dönemi'), { target: { value: 'hourly' } });
    fireEvent.change(screen.getByLabelText('Anlaşma türü'), { target: { value: 'net' } });
    expect(screen.getByLabelText('Saatlik net tutar (TRY)')).toBeInTheDocument();
    expect(screen.getByLabelText('Dönem başı gerçek kümülatif GV matrahı')).toHaveValue(null);
    expect(axios.post).not.toHaveBeenCalled();
  });
  it('automatically displays backend-calculated counterparts', async () => {
    render(<Form initial={complete()} />);
    await waitFor(() => expect(screen.getByText('Hesaplanan dönem neti:')).toBeInTheDocument());
    expect(axios.post).toHaveBeenCalledWith('/hr/salary/preview', expect.objectContaining({ opening_tax_base: '0' }), expect.anything());
    expect(screen.getByText(/Hesaplanan dönem neti:/)).toHaveTextContent('₺28.075,50');
  });
  it('clears a prior result immediately when an input changes', async () => {
    render(<Form initial={complete()} />);
    await screen.findByText('Hesaplanan dönem brütü:');
    fireEvent.change(screen.getByLabelText('Dönem başı gerçek kümülatif GV matrahı'), { target: { value: '' } });
    expect(screen.queryByText('Hesaplanan dönem brütü:')).not.toBeInTheDocument();
  });
  it('shows backend validation instead of a made-up result', async () => {
    axios.post.mockRejectedValue({ response: { data: { detail: 'Matrah dönemi geçersiz' } } });
    render(<Form initial={complete()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Matrah dönemi geçersiz');
  });
});
