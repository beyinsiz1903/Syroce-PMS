import React from 'react';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import AgencyOnboardingPanel from '@/components/agency/AgencyOnboardingPanel';
import AgencyActivate from '../AgencyActivate';

const isolated = vi.hoisted(() => ({ post: vi.fn(), interceptors: { request: { use: vi.fn() } } }));
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), create: vi.fn(() => isolated) } }));
const report = {
  ready: false, checks: { agency_active: true, portal_user_active: false, contract_approved: false, sellable_offer: false },
  active_users: 0, contract_count: 0, invitations: [], offers: [], checked_at: '2026-10-13T10:00:00Z', scope: 'Anlık kontrol',
};
beforeEach(() => { vi.clearAllMocks(); axios.get.mockResolvedValue({ data: report }); window.history.replaceState({}, '', '/'); });
afterEach(cleanup);

it('shows incomplete steps and sends explicit invitation without password or API key', async () => {
  axios.post.mockResolvedValue({ data: { email_sent: true, message: 'Davet e-posta sağlayıcısına iletildi' } });
  render(<AgencyOnboardingPanel agency={{ id: 'a', status: 'active', contact_email: 'agent@example.com' }} />);
  expect(await screen.findByText('Satışa hazır değil')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Yetkili adı soyadı'), { target: { value: 'Agent Name' } });
  fireEvent.click(screen.getByRole('button', { name: 'Davet gönder / yenile' }));
  expect(await screen.findByText('Davet e-posta sağlayıcısına iletildi')).toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledWith('/marketplace/v1/admin/agencies/a/invitations', { name: 'Agent Name', email: 'agent@example.com' });
});

it('shows failed delivery and never confuses it with activation', async () => {
  axios.post.mockResolvedValue({ data: { email_sent: false, message: 'E-posta gönderilemedi' } });
  render(<AgencyOnboardingPanel agency={{ id: 'a', status: 'active', contact_email: 'agent@example.com' }} />);
  await screen.findByText('Satışa hazır değil');
  fireEvent.change(screen.getByLabelText('Yetkili adı soyadı'), { target: { value: 'Agent Name' } });
  fireEvent.click(screen.getByRole('button', { name: 'Davet gönder / yenile' }));
  expect(await screen.findByText('E-posta gönderilemedi')).toBeInTheDocument();
  expect(screen.queryByText('Satışa hazır — seçilen tarihler için')).not.toBeInTheDocument();
});

it('clears old readiness when dates change and fails closed on network errors', async () => {
  axios.get.mockResolvedValueOnce({ data: { ...report, ready: true } }).mockRejectedValueOnce(new Error('offline'));
  render(<AgencyOnboardingPanel agency={{ id: 'a', status: 'active' }} />);
  await screen.findByText('Satışa hazır — seçilen tarihler için');
  fireEvent.change(screen.getByLabelText('Kontrol giriş tarihi'), { target: { value: '2027-03-01' } });
  expect(await screen.findByRole('alert')).toHaveTextContent('İşlem tamamlanamadı');
  expect(screen.queryByText('Satışa hazır — seçilen tarihler için')).not.toBeInTheDocument();
});

it('activates with fragment token and scrubs browser URL without storing credentials', async () => {
  window.history.replaceState({}, '', `/agency-activate#token=${'x'.repeat(43)}`);
  isolated.post.mockResolvedValue({ data: { ok: true } });
  render(<MemoryRouter><AgencyActivate /></MemoryRouter>);
  expect(window.location.hash).toBe('');
  fireEvent.change(screen.getByLabelText('Yeni şifre'), { target: { value: 'SecureAgency2026!' } });
  fireEvent.change(screen.getByLabelText('Şifre tekrar'), { target: { value: 'SecureAgency2026!' } });
  fireEvent.click(screen.getByRole('button', { name: 'Şifremi belirle ve etkinleştir' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Şifreniz oluşturuldu'));
  expect(isolated.post).toHaveBeenCalledWith('/marketplace/v1/extranet/invitations/accept', { token: 'x'.repeat(43), password: 'SecureAgency2026!' });
});

it('rejects mismatching passwords before network and displays expired invitation errors', async () => {
  window.history.replaceState({}, '', `/agency-activate#token=${'x'.repeat(43)}`);
  isolated.post.mockRejectedValue({ response: { data: { detail: 'Davet süresi dolmuş.' } } });
  render(<MemoryRouter><AgencyActivate /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Yeni şifre'), { target: { value: 'SecureAgency2026!' } });
  fireEvent.change(screen.getByLabelText('Şifre tekrar'), { target: { value: 'Different2026!' } });
  fireEvent.click(screen.getByRole('button', { name: 'Şifremi belirle ve etkinleştir' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Şifreler eşleşmiyor');
  expect(isolated.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Şifre tekrar'), { target: { value: 'SecureAgency2026!' } });
  fireEvent.click(screen.getByRole('button', { name: 'Şifremi belirle ve etkinleştir' }));
  expect(await screen.findByText('Davet süresi dolmuş.')).toBeInTheDocument();
});

it('does not offer activation without an invitation', () => {
  render(<MemoryRouter><AgencyActivate /></MemoryRouter>);
  expect(screen.getByRole('alert')).toHaveTextContent('Davet bağlantısı bulunamadı');
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
