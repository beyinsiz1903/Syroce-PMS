import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import ProcurementPage, { comparableOpenCommitment } from '../ProcurementPage';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('@/components/EntityHistoryDrawer', () => ({ default: () => null }));
vi.mock('../ProcurementB2BTab', () => ({ default: () => null }));

// Review of #1371 (Codex): an EUR 100 open order against a TRY 100 limit
// was shown as 100 % used.
it('does not report 100 EUR as 100 percent utilization of a 100 TRY credit limit', async () => {
  const supplier = { id: 's', name: 'Artificial supplier', active: true, currency: 'TRY', credit_limit: 100,
    open_commitment: 100, open_commitment_by_currency: { EUR: 100 } };
  axios.get.mockImplementation(async url => ({ data: url.startsWith('/procurement/suppliers') ? { items: [supplier] } : {} }));
  render(<MemoryRouter><ProcurementPage user={{ role: 'admin' }} tenant={{ currency: 'TRY' }} /></MemoryRouter>);
  await screen.findAllByText('Artificial supplier');
  expect(screen.queryByText('100%')).not.toBeInTheDocument();
});

describe('comparableOpenCommitment', () => {
  it('compares only amounts in the limit currency', () => {
    expect(comparableOpenCommitment({ currency: 'TRY', open_commitment: 100, open_commitment_by_currency: { EUR: 100 } })).toBeNull();
    expect(comparableOpenCommitment({ limit_currency: 'EUR', open_commitment_by_currency: { EUR: 60 } })).toBe(60);
    expect(comparableOpenCommitment({ currency: 'TRY', open_commitment_by_currency: { TRY: 40, USD: 5 } })).toBeNull();
    expect(comparableOpenCommitment({ open_commitment: 0, open_commitment_by_currency: {} }, 'TRY')).toBe(0);
  });
});
