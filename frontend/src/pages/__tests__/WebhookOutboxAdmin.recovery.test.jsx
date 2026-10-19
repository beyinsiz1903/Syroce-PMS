import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import WebhookOutboxAdmin from '../WebhookOutboxAdmin';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/components/ui/page-header', () => ({ PageHeader: ({ title }) => <h1>{title}</h1> }));

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockImplementation(async (url) => ({ data:
    url === '/outbox/events' ? { events: [{ id: 'event', tenant_id: 'hotel', status: 'failed',
      last_error: 'exely_room_mapping_missing', event_type: 'booking.cancelled.v1' }] } :
    url.endsWith('/readiness') ? { can_requeue: false, issues: ['exely_room_mapping_missing'] } : {}
  }));
  axios.post.mockResolvedValue({ data: { success: true } });
});

it('checks configuration read-only and keeps requeue blocked while mapping is missing', async () => {
  render(<WebhookOutboxAdmin />);
  const check = await screen.findByRole('button', { name: 'Yapılandırmayı kontrol et' });
  expect(screen.getByRole('button', { name: 'Requeue' })).toBeDisabled();
  fireEvent.click(check);
  expect(await screen.findByText('Önce düzeltin: exely_room_mapping_missing')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Requeue' })).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('requires explicit requeue after a successful read-only check', async () => {
  const implementation = axios.get.getMockImplementation();
  axios.get.mockImplementation(async (url, ...args) => url.endsWith('/readiness')
    ? { data: { can_requeue: true, issues: [] } } : implementation(url, ...args));
  render(<WebhookOutboxAdmin />);
  fireEvent.click(await screen.findByRole('button', { name: 'Yapılandırmayı kontrol et' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Requeue' })).toBeEnabled());
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Requeue' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/outbox/event/requeue'));
});
