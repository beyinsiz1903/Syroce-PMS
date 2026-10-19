import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import { SettingsTab } from '../MessagingDashboard';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }) }));

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockResolvedValue({ data: { email: {
    health_status: 'unhealthy', health_error: 'SMTP bağlantısı zaman aşımına uğradı; Zoho HTTPS API kullanın.',
    is_sandbox: false, enabled: true,
    credentials: { email_transport: 'smtp', smtp_host: 'smtppro.zoho.eu', from_email: 'synthetic@example.test' },
  } } });
});

it('keeps the actionable SMTP error visible without changing or sending anything', async () => {
  render(<SettingsTab />);
  expect(await screen.findByRole('alert')).toHaveTextContent('SMTP bağlantısı zaman aşımına uğradı');
  expect(screen.getByText(/SMTP çıkışı kısıtlı sunucularda/)).toHaveTextContent('HTTPS API (443)');
  expect(axios.post).not.toHaveBeenCalled();
});

it('shows OAuth fields on explicit selection but never auto-saves a provider switch', async () => {
  render(<SettingsTab />);
  const select = await screen.findByLabelText('Gönderim yöntemi');
  fireEvent.change(select, { target: { value: 'zoho_api' } });
  expect(screen.getByText(/SMTP şifresi yerine Zoho OAuth bilgileri gerekir/)).toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
});
