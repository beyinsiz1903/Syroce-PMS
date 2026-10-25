import { afterEach, describe, expect, it, vi } from 'vitest';
import { canVoidFolioEvent, folioEventBalanceEffect, folioEventCategoryLabel, folioEventTitle } from '@/lib/folioPayments';
import { printFolio } from '@/components/pms/PrintTemplates';

afterEach(() => vi.restoreAllMocks());
describe('signed settlement timeline and print', () => {
  it.each(['barter', 'write_off', 'wallet', 'gift_card_redemption', 'loyalty_redemption', 'city_ledger'])(
    'does not call %s cash or expose its generic void button', method => {
      const application = { type: 'payment', category: method, amount: 2, billing_settlement_id: 'source' };
      const undo = { ...application, type: 'refund', amount: -2, payment_type: 'refund' };
      expect(folioEventBalanceEffect(application)).toBe(-2);
      expect(folioEventBalanceEffect(undo)).toBe(2);
      expect(folioEventTitle(application)).not.toContain('tahsilatı');
      expect(folioEventTitle(undo)).toContain('ters kayıt');
      expect(canVoidFolioEvent(application)).toBe(false);
      expect(canVoidFolioEvent(undo)).toBe(false);
      expect(folioEventCategoryLabel(application)).not.toBe(method);
    },
  );
  it('leaves pending cash and protected cheque clearance outside the generic void path', () => {
    expect(folioEventBalanceEffect({ type: 'payment', method: 'cash', status: 'pending', amount: 50 })).toBe(-0);
    expect(canVoidFolioEvent({ type: 'payment', method: 'cash', status: 'pending', amount: 50 })).toBe(false);
    expect(canVoidFolioEvent({ type: 'payment', method: 'bank_transfer', billing_settlement_id: 'cheque', amount: 50 })).toBe(false);
    expect(canVoidFolioEvent({ type: 'payment', method: 'cash', amount: 50 })).toBe(true);
    expect(folioEventBalanceEffect({ type: 'refund', amount: 2, method: 'cash' })).toBe(2);
  });
  it('prints reversals in the debit column, separates collection from settlement, and escapes text', () => {
    const write = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue({ document: { write, close: vi.fn() }, print: vi.fn() });
    printFolio({ folio: { folio_number: 'F<&', currency: 'USD' },
      summary: { total_charges: 20, total_payments: 0, cash_collection_total: 0, non_cash_settlement_total: 0, balance: 20 },
      timeline: [
        { type: 'charge', description: '<img src=x>', amount: 20, balance_effect: 20, running_balance: 20 },
        { type: 'payment', method: 'barter', amount: 2, balance_effect: -2, running_balance: 18 },
        { type: 'refund', method: 'barter', payment_type: 'refund', amount: -2, balance_effect: 2, running_balance: 20 },
      ] }, { name: 'Demo' });
    const html = write.mock.calls[0][0];
    expect(html).toContain('&lt;img src=x&gt;');
    expect(html).not.toContain('<img src=x>');
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const rows = doc.querySelectorAll('tbody tr');
    expect(rows[1].children[3].textContent).toBe('');
    expect(rows[1].children[4].textContent).toContain('2,00');
    expect(rows[2].children[3].textContent).toContain('2,00');
    expect(rows[2].children[4].textContent).toBe('');
    expect(rows[2].children[5].textContent).toContain('20,00');
    expect(doc.body.textContent).toContain('Net tahsilat');
    expect(doc.body.textContent).toContain('Nakit dışı mahsup');
  });
});
