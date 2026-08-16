import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReportScheduler from '../ReportScheduler';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));

describe('ReportScheduler', () => {
  beforeEach(() => {
    window.localStorage.setItem('token', 'test-token');
    vi.spyOn(global, 'fetch').mockImplementation(async (url) => {
      const path = String(url);
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
        return { ok: true, json: async () => ({ history: [] }) };
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
  });

  it('renders schedule actions when schedules exist', async () => {
    render(<ReportScheduler />);

    await waitFor(() => expect(screen.getByText('Test zamanlaması')).toBeInTheDocument());
    expect(screen.getByText('Günlük Özet Raporu')).toBeInTheDocument();
  });
});
