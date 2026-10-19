import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import MaintenanceReports from '@/components/MaintenanceReports';

// Ported from the 2026-10-19 report acceptance audit.
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => (typeof fallback === 'string' ? fallback : key), i18n: { language: 'tr' } }) }));

class Boundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div data-testid="audit-boundary">REPORT CRASH</div> : this.props.children; }
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('maintenance initial network failure is a retryable report error, not a render crash', async () => {
  axios.get.mockRejectedValue(new Error('isolated unavailable server'));
  render(<Boundary><MaintenanceReports /></Boundary>);
  await waitFor(() => expect(screen.queryByText('cm.components_MaintenanceReports.yukleniyor')).not.toBeInTheDocument());
  expect(screen.queryByTestId('audit-boundary')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toBeInTheDocument();

  axios.get.mockResolvedValue({ data: { period: { week_number: 43, start: '2026-10-19', end: '2026-10-25' }, summary: { total_tasks: 7 }, by_category: {}, by_priority: {}, top_issues: [], tasks: [] } });
  fireEvent.click(screen.getByRole('button', { name: 'Tekrar dene' }));
  expect(await screen.findByText('7')).toBeInTheDocument();
});

it('switching maintenance from a loaded weekly report to monthly must not crash before the request starts', async () => {
  axios.get.mockResolvedValue({ data: { period: { week_number: 43, start: '2026-10-19', end: '2026-10-25' }, summary: {}, by_category: {}, by_priority: {}, top_issues: [], tasks: [] } });
  render(<Boundary><MaintenanceReports /></Boundary>);
  const monthly = await screen.findByRole('button', { name: 'cm.components_MaintenanceReports.aylik' });
  fireEvent.click(monthly);
  expect(screen.queryByTestId('audit-boundary')).not.toBeInTheDocument();
});
