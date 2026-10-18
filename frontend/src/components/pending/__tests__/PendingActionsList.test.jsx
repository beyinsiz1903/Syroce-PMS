import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PendingActionsList from '../PendingActionsList';

const data = {
  counts: { yours: 2, theirs: 1, overdue: 1 },
  yours: [
    { kind: 'payment', owner: 'yours', record_id: 's1', target: 'statements', party_name: 'Demo Otel', ref: 'EKS-2026-0001', amount: 5600, currency: 'TRY', due_date: '2026-10-08', overdue: true },
    { kind: 'contract_amendment', owner: 'yours', record_id: 'c1', target: 'contracts', party_name: 'Demo Otel', ref: 'SOZ-2026-0014' },
  ],
  theirs: [
    { kind: 'payment_notice', owner: 'theirs', record_id: 's2', notice_id: 'n1', target: 'statements', party_name: 'Demo Otel', amount: 400, currency: 'TRY', payment_ref: 'EFT-1' },
  ],
};

describe('PendingActionsList', () => {
  it('splits own work from what waits for the other side, overdue first', () => {
    render(<PendingActionsList data={data} onOpen={() => {}} />);
    expect(screen.getByText(/Sizin işiniz \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/1 vadesi geçmiş/)).toBeInTheDocument();
    expect(screen.getByTestId('pending-payment-yours')).toHaveTextContent('Ödemeniz bekleniyor');
    expect(screen.getByTestId('pending-payment-yours')).toHaveTextContent('Vadesi geçti 2026-10-08');
    expect(screen.getByTestId('pending-contract_amendment-yours')).toHaveTextContent('kararınızı bekliyor');
    expect(screen.getByTestId('pending-payment_notice-theirs')).toHaveTextContent('doğrulama bekliyor');
    expect(screen.getByTestId('pending-payment_notice-theirs')).toHaveTextContent('Ref. EFT-1');
  });

  it('opens the item with its target', () => {
    const onOpen = vi.fn();
    render(<PendingActionsList data={data} onOpen={onOpen} />);
    fireEvent.click(screen.getAllByRole('button', { name: /İşleme al/ })[1]);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ kind: 'contract_amendment', target: 'contracts' }));
  });

  it('says so when nothing is pending', () => {
    render(<PendingActionsList data={{ yours: [], theirs: [] }} />);
    expect(screen.getByTestId('pending-empty')).toHaveTextContent('Bekleyen iş yok.');
  });
});
