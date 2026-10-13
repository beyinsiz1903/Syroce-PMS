import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import AgencyIntegrationRepairs from '../AgencyIntegrationRepairs';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());
const renderPage = () => render(<MemoryRouter><AgencyIntegrationRepairs /></MemoryRouter>);
const row = (status) => ({ id: 'b', tenant_id: 't', agency_id: 'a', confirmation_code: 'MKT-1', integration: { status, done: ['ledger'], attempts: 8, last_error: 'folio:RuntimeError' } });

it('shows existing booking and retries only its missing integration', async () => {
  axios.get.mockResolvedValue({ data: { items: [row('failed')], total: 1 } });
  axios.post.mockResolvedValue({ data: { ok: true } });
  renderPage();
  await screen.findByText('MKT-1');
  expect(screen.getByText(/Yeniden rezervasyon oluşturmayın/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Eksik işlemleri tekrar dene' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/marketplace/v1/admin/integrations/b/retry'));
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
});

it('cannot retry an active worker and never shows an empty success on load failure', async () => {
  axios.get.mockResolvedValueOnce({ data: { items: [row('processing')], total: 1 } }).mockRejectedValue(new Error('failed'));
  renderPage();
  await screen.findByText('MKT-1');
  expect(screen.getByRole('button', { name: 'Eksik işlemleri tekrar dene' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Liste alınamadı');
  expect(axios.post).not.toHaveBeenCalled();
});
