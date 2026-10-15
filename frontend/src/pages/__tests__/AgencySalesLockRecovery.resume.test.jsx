import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import AgencySalesLockRecovery from '../AgencySalesLockRecovery';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const lock = {
  lock_id: 'k1', owner: 'dead-writer-1', tenant_id: 't', agency_id: 'a', operation: 'marketplace_modification',
  recovery_state: 'active', resumable: true, modification_verified: false, proposal: { id: 'p', status: 'applying' },
};

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockResolvedValue({ data: { items: [lock], total: 1 } });
  axios.post.mockResolvedValue({ data: { ok: true } });
});

it('hands a crashed modification fence to its resume only after attestation', async () => {
  render(<MemoryRouter><AgencySalesLockRecovery /></MemoryRouter>);
  const button = await screen.findByRole('button', { name: 'Devam için serbest bırak' });
  fireEvent.click(button);
  expect(axios.post).not.toHaveBeenCalled();
  expect(screen.getByRole('alert')).toHaveTextContent('durduğunu onaylayın');

  fireEvent.change(screen.getByPlaceholderText('Uzlaştırma gerekçesi'), { target: { value: 'Süreç çöktü, loglar incelendi' } });
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(button);
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    '/marketplace/v1/admin/sales-locks/k1/release-for-resume',
    { owner: 'dead-writer-1', reason: 'Süreç çöktü, loglar incelendi', writer_stopped_confirmed: true },
  ));
});
