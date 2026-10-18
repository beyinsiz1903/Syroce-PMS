import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import AdminHub from '../AdminHub';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback || key }) }));
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); axios.get.mockResolvedValue({ data: { open_count: 3, new_count: 2, notifications: [], unread_count: 0 } }); });

it('shows a direct platform request entry and live counts without opening price management', async () => {
  render(<MemoryRouter><AdminHub user={{ id: 'root', role: 'super_admin' }} /></MemoryRouter>);
  expect(await screen.findByText('3 açık · 2 yeni')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Satış ve modül talepleri/ })).toHaveAttribute('href', '/admin/module-requests');
});

it('does not expose the platform sales entry to a hotel administrator', () => {
  render(<MemoryRouter><AdminHub user={{ id: 'hotel', role: 'admin' }} /></MemoryRouter>);
  expect(screen.queryByText('Satış ve modül talepleri')).not.toBeInTheDocument();
  expect(axios.get).not.toHaveBeenCalled();
});
