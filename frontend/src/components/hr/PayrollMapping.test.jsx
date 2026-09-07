import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import PayrollMapping from './PayrollMapping';
vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

it('loads existing mapping and submits the separate liability codes', async () => {
  axios.get.mockResolvedValue({ data: { mapping: { wage_expense_code: '770', employer_expense_code: '770.02', net_payable_code: '335', withholding_payable_code: '360', sgk_payable_code: '361', advance_receivable_code: '196' } } });
  axios.put.mockResolvedValue({});
  render(<PayrollMapping />);
  fireEvent.click(screen.getByText('Muhasebe Hesap Eşlemesini Aç'));
  await screen.findByLabelText('SGK ve işsizlik borcu (ör. 361)');
  fireEvent.click(screen.getByText('Hesap Eşlemesini Kaydet'));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith('/payroll-gl/mapping', {
    wage_expense_code: '770', employer_expense_code: '770.02', net_payable_code: '335',
    withholding_payable_code: '360', sgk_payable_code: '361', advance_receivable_code: '196', other_deductions_code: null,
  }));
});

it('does not expose a settings form after permission denial', async () => {
  axios.get.mockRejectedValue({ response: { status: 403 } });
  render(<PayrollMapping />);
  fireEvent.click(screen.getByText('Muhasebe Hesap Eşlemesini Aç'));
  expect(await screen.findByRole('status')).toHaveTextContent('yetkinizi kontrol edin');
  expect(screen.queryByText('Hesap Eşlemesini Kaydet')).toBeNull();
});
