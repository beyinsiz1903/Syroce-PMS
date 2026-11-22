import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { JournalSourceDetails } from '@/pages/accounting/JournalSourceDetails';

afterEach(cleanup);
it('exposes the original funding identifier and liability credit without claiming available funds', () => {
  const journal = { id: 'funding-original-uuid', status: 'posted', entry_hash: 'hash', memo: 'Kaynak fonlama', lines: [
    { account_code: '100', debit_minor: 10000, credit_minor: 0 },
    { account_code: '336', debit_minor: 0, credit_minor: 10000, currency: 'USD', foreign_amount_minor: 250 },
  ] };
  render(<JournalSourceDetails journal={journal} accounts={[{ code: '336', name: 'Diğer Borçlar' }]} />);
  fireEvent.click(screen.getByText('Fiş detayını ve kaynak kimliğini göster'));
  const field = screen.getByLabelText('Kaynak fiş kimliği');
  expect(field).toHaveValue('funding-original-uuid');
  expect(field).toHaveAttribute('readonly');
  fireEvent.focus(field);
  expect(field.selectionEnd).toBe(journal.id.length);
  const liability = screen.getByText('336 · Diğer Borçlar').closest('tr');
  expect(within(liability).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['336 · Diğer Borçlar', '₺0,00', '₺100,00', '$2.50']);
  expect(screen.getByText(/kullanılabilir bakiye garantisi değildir/)).toBeInTheDocument();
  expect(screen.getByText(/bütünlük sonucu ayrıca denetlenir/)).toBeInTheDocument();
  expect(journal.lines[1].credit_minor).toBe(10000);
});
it('keeps unsealed, reversed and missing-line evidence explicit', () => {
  render(<JournalSourceDetails journal={{ id: 'old', reversal_status: 'reversed', lines: [] }} />);
  expect(screen.getByText(/Ters kaydı var/)).toBeInTheDocument();
  expect(screen.getByText(/Özgün mühür bilgisi yok/)).toBeInTheDocument();
  expect(screen.getByText(/satır ayrıntıları yok/)).toBeInTheDocument();
});
