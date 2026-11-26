import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/components/night-audit/tabs/PreparationTab', () => ({ default: () => null }));
import NightAuditDashboard from '../NightAuditDashboard';
const simulation = { id: 'sim', business_date: '2026-11-12', dry_run: true, status: 'dry_run_completed', total_room_revenue: 4324.32 };
const completed = { id: 'real', business_date: '2026-11-11', status: 'completed', total_room_revenue: 2702.70, total_tax_amount: 297.30, total_payments_amount: 4900, rooms_processed: 2 };
let actual;
beforeEach(() => {
 actual = completed;
 get.mockReset().mockImplementation(async (url, config) => {
  if (url === '/night-audit/business-date') return { data: { business_date: '2026-11-12', previous_business_date: '2026-11-11' } };
  if (url === '/night-audit/history') return { data: config.params.completed_only
   ? { runs: actual ? [actual] : [], total: actual ? 1 : 0 }
   : { runs: Array.from({ length: 20 }, (_, i) => ({ ...simulation, id: `sim-${i}` })), total: 239 } };
  return { data: {} };
 });
});
afterEach(cleanup);
const mount = () => render(<MemoryRouter><NightAuditDashboard user={{ role: 'super_admin' }} tenant={{ currency: 'TRY' }} /></MemoryRouter>);
const card = label => screen.getByText(label).parentElement.parentElement;
it('uses the real completed close even after a full page of simulations', async () => {
 mount();
 await waitFor(() => expect(card('Son Oda Geliri')).toHaveTextContent('2.702,70'));
 expect(card('Son Oda Geliri')).not.toHaveTextContent('4.324,32');
 expect(card('Son Oda Geliri')).toHaveTextContent('2026-11-11');
 expect(card('Son Tahsilat')).toHaveTextContent('4.900,00');
 expect(card('Toplam Denetim')).toHaveTextContent('Bugün bekliyor');
 expect(get).toHaveBeenCalledWith('/night-audit/financial-summary', { params: { date: '2026-11-11' } });
});
it.each([null, { ...simulation, status: 'completed' }])('does not promote missing or legacy dry-run data to realized money: %s', async value => {
 actual = value; mount();
 await waitFor(() => expect(card('Son Oda Geliri')).toHaveTextContent('Tamamlanan gerçek gün sonu bulunamadı'));
 expect(card('Son Oda Geliri')).not.toHaveTextContent('4.324,32');
 expect(card('Son Tahsilat')).not.toHaveTextContent('4.900,00');
});

it('waits for history before selecting finance day instead of racing current day', async () => {
 const normal = get.getMockImplementation();
 let releaseHistory;
 const ready = new Promise(resolve => { releaseHistory = resolve; });
 get.mockImplementation(async (url, config) => {
  if (url === '/night-audit/history') await ready;
  return normal(url, config);
 });
 mount();
 await waitFor(() => expect(get).toHaveBeenCalledWith('/night-audit/business-date'));
 await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
 expect(get.mock.calls.filter(([url]) => url === '/night-audit/financial-summary')).toEqual([]);
 await act(async () => { releaseHistory(); });
 await waitFor(() => expect(get).toHaveBeenCalledWith('/night-audit/financial-summary', { params: { date: '2026-11-11' } }));
 expect(get.mock.calls.filter(([url]) => url === '/night-audit/financial-summary').every(([, config]) => config.params.date === '2026-11-11')).toBe(true);
});
