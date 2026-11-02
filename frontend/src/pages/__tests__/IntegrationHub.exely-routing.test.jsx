import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('axios', () => ({ default: api }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
import IntegrationHub from '@/pages/IntegrationHub';

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async path => ({ data: path.endsWith('/dashboard') ? {
    connectors: [{ connector_id: 'old-exely', provider: 'exely', status: 'paused', health: 'red' }],
  } : {} }));
});

it.each(['Müsaitliği yönet', 'Fiyatları yönet'])('opens the scoped editor for %s, without an unscoped legacy sync', async label => {
  render(<MemoryRouter><Routes>
    <Route path="/" element={<IntegrationHub />} />
    <Route path="/unified-rate-manager" element={<p>Scoped rate editor</p>} />
  </Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: label }));
  expect(await screen.findByText('Scoped rate editor')).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});
