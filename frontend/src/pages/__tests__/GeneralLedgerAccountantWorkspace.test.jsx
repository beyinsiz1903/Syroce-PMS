import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { buildAccountLedgerRows } from '@/pages/accounting/AccountLedgerView';
import { GeneralLedgerNavigation, GL_NAV_GROUPS } from '@/pages/accounting/GeneralLedgerNavigation';

describe('General ledger accountant workspace', () => {
  it('keeps every general-ledger destination in the expanded left menu', () => {
    expect(GL_NAV_GROUPS.map((group) => group.label)).toEqual([
      'Ticari İşlemler',
      'Günlük İşlemler',
      'Defter ve Raporlar',
      'Dönem ve Kontrol',
    ]);
    expect(GL_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.value))).toEqual([
      'invoices-menu',
      'current-accounts',
      'overview',
      'journals',
      'account-ledger',
      'accounts',
      'trial-balance',
      'statements',
      'periods',
      'workspace',
      'integrations',
      'setup',
    ]);
    const commerce = GL_NAV_GROUPS[0];
    expect(commerce.items[0].children).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: 'Yeni Fatura', href: '/app/invoices?action=new' }),
      expect.objectContaining({ label: 'Fatura Listesi', href: '/app/invoices?tab=invoices' }),
      expect.objectContaining({ label: 'Nilvera Entegrasyonu', targetTab: 'integrations' }),
    ]));
    expect(commerce.items[1]).toMatchObject({ label: 'Cariler', href: '/city-ledger' });
  });

  it('opens existing invoice, current-account and Nilvera destinations without creating duplicate modules', () => {
    const onSelect = vi.fn();
    const onNavigate = vi.fn();
    render(<GeneralLedgerNavigation activeTab="overview" onSelect={onSelect} onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole('button', { name: 'Yeni Fatura' }));
    expect(onNavigate).toHaveBeenCalledWith('/app/invoices?action=new');

    fireEvent.click(screen.getByRole('button', { name: 'Cariler' }));
    expect(onNavigate).toHaveBeenCalledWith('/city-ledger');

    fireEvent.click(screen.getByRole('tab', { name: 'Nilvera Entegrasyonu' }));
    expect(onSelect).toHaveBeenCalledWith('integrations');
  });

  it('builds a filterable account ledger with per-account running balances', () => {
    const result = buildAccountLedgerRows([
      {
        id: 'entry-2',
        date: '2026-08-02',
        entry_no: 'YEV-2026-0002',
        memo: 'Kasa tahsilatı',
        lines: [
          { account_code: '100', debit: 50, credit: 0 },
          { account_code: '120', debit: 0, credit: 50 },
        ],
      },
      {
        id: 'entry-1',
        date: '2026-08-01',
        entry_no: 'YEV-2026-0001',
        memo: 'Açılış',
        lines: [{ account_code: '100', debit: 100, credit: 0 }],
      },
      {
        id: 'entry-3',
        date: '2026-08-03',
        entry_no: 'YEV-2026-0003',
        memo: 'Kasa ödemesi',
        lines: [{ account_code: '100', debit: 0, credit: 25 }],
      },
    ], [
      { code: '100', name: 'Kasa' },
      { code: '120', name: 'Alıcılar' },
    ], { account: '100 Kasa', start: '2026-08-01', end: '2026-08-03' });

    expect(result.rows.map((row) => ({ documentNo: row.documentNo, balance: row.balance }))).toEqual([
      { documentNo: 'YEV-2026-0001', balance: 100 },
      { documentNo: 'YEV-2026-0002', balance: 150 },
      { documentNo: 'YEV-2026-0003', balance: 125 },
    ]);
    expect(result.totals).toEqual({ debit: 150, credit: 25 });
  });

  it('filters ledger rows by explanation and document number', () => {
    const result = buildAccountLedgerRows([{
      id: 'entry-1',
      date: '2026-08-01',
      entry_no: 'YEV-2026-0042',
      memo: 'Banka virmanı',
      lines: [{ account_code: '102', debit_minor: 12500, credit_minor: 0 }],
    }], [{ code: '102', name: 'Bankalar' }], { description: 'virman', document: '0042' });

    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]).toMatchObject({ accountCode: '102', accountName: 'Bankalar', debit: 125 });
  });
});
