import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import QualityManagement from '@/pages/QualityManagement';

vi.mock('axios');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('QualityManagement contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockImplementation((url) => {
      if (url === '/quality/dashboard') return Promise.resolve({ data: { summary: { open: 2, overdue: 1, critical: 1, closed: 3, closure_rate: 60, by_kind: {}, by_department: {} } } });
      if (url === '/quality/records') return Promise.resolve({ data: { records: [{ id: 'q1', _kind: 'quality_capa', title: 'Tekrarlayan temizlik hatası', department: 'Kat Hizmetleri', severity: 'high', status: 'open' }] } });
      return Promise.resolve({ data: { entries: [], summary: {} } });
    });
  });

  it('renders operational quality metrics and records', async () => {
    render(<QualityManagement />);
    expect(screen.getByRole('heading', { name: 'Kalite Yönetimi' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Tekrarlayan temizlik hatası')).toBeInTheDocument());
    expect(screen.getByText('Kapanış oranı')).toBeInTheDocument();
  });

  it('loads dashboard, register and feedback without serial blocking', async () => {
    render(<QualityManagement />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(3));
    expect(axios.get).toHaveBeenCalledWith('/quality/dashboard');
    expect(axios.get).toHaveBeenCalledWith('/quality/records', { params: { limit: 500 } });
  });
});
