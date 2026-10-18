import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReportScheduler from '../ReportScheduler';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));

describe('ReportScheduler', () => {
  let sendResult;
  let history;
  beforeEach(() => {
    sendResult = { status: 'sent' };
    history = [];
    window.localStorage.setItem('token', 'test-token');
    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const path = String(url);
      if (path.includes('/send-now') || path.includes('/retry')) {
        return { ok: true, json: async () => sendResult };
      }
      if (path.includes('/schedules')) {
        return {
          ok: true,
          json: async () => ({
            schedules: [{
              _id: 'schedule-1',
              name: 'Test zamanlaması',
              report_type: 'daily_summary',
              frequency: 'daily',
              format: 'pdf',
              send_time: '08:00',
              recipients: ['test@example.invalid'],
              is_active: true,
            }],
          }),
        };
      }
      if (path.includes('/history')) {
        if (path.includes('/history/snapshot')) {
          return { ok: true, json: async () => ({ entry: { ...history[0], report_payload: { rows: [{ label: 'Snapshot revenue', value: 'TRY 700.00' }], notes: 'İşlenmiş gelir; tahsilat değildir.' } } }) };
        }
        return { ok: true, json: async () => ({ history }) };
      }
      if (path.includes('/report-types')) {
        return {
          ok: true,
          json: async () => ({
            report_types: [{ key: 'daily_summary', label: 'Günlük Özet Raporu' }],
          }),
        };
      }
      throw new Error(`unexpected request: ${path}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.history.replaceState(null, '', '/');
  });

  it('renders schedule actions when schedules exist', async () => {
    render(<ReportScheduler />);

    await waitFor(() => expect(screen.getByText('Test zamanlaması')).toBeInTheDocument());
    expect(screen.getByText('Günlük Özet Raporu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Test zamanlaması raporunu şimdi gönder' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Test zamanlaması zamanlamasını duraklat' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Test zamanlaması zamanlamasını düzenle' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Test zamanlaması zamanlamasını sil' })).toBeInTheDocument();
  });

  it('shows a failed send returned with HTTP 200 instead of silently clearing it', async () => {
    sendResult = { status: 'failed', message: 'PDF üretilemedi; dosya gönderilmedi.' };
    render(<ReportScheduler />);
    fireEvent.click(await screen.findByRole('button', { name: 'Test zamanlaması raporunu şimdi gönder' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('PDF üretilemedi; dosya gönderilmedi.');
  });

  it('allows a partial delivery retry and exposes the reporting period control', async () => {
    history = [{ _id: 'h', schedule_name: 'Partial report', status: 'partial', recipients: ['test@example.invalid'] }];
    render(<ReportScheduler />);
    fireEvent.click(await screen.findByRole('button', { name: 'Test zamanlaması zamanlamasını düzenle' }));
    const period = screen.getByLabelText('Rapor dönemi');
    expect(period).toHaveValue('auto');
    fireEvent.change(period, { target: { value: 'previous_month' } });
    expect(period).toHaveValue('previous_month');
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'cm.pages_ReportScheduler.gonderim_gecmisi' }), { button: 0, ctrlKey: false });
    expect(await screen.findByRole('button', { name: 'Partial report gönderimini tekrar dene' })).toBeInTheDocument();
  });

  it('opens the immutable report referenced by the email link', async () => {
    window.history.replaceState(null, '', '/report-scheduler?history_id=snapshot');
    history = [{ _id: 'snapshot', schedule_name: 'Original report', report_range: '01.10.2026 – 07.10.2026', format: 'link', status: 'sent', delivery_details: { sent_count: 1 } }];
    render(<ReportScheduler />);
    expect(await screen.findByRole('dialog')).toHaveTextContent('Snapshot revenue: TRY 700.00');
    expect(screen.getByRole('dialog')).toHaveTextContent('01.10.2026 – 07.10.2026');
    expect(screen.getByRole('dialog')).toHaveTextContent('İşlenmiş gelir; tahsilat değildir.');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/history/snapshot'), expect.any(Object));
  });
});
