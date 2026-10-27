import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import MessagingDashboard, { SendTab } from '../MessagingDashboard';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));

const provider = { enabled: true, is_sandbox: false, health_status: 'healthy', credentials: { smtp_host: 'smtp.example.com', from_email: 'hotel@example.com' } };
let settings, profile;
beforeEach(() => {
  vi.clearAllMocks();
  settings = { email: provider };
  profile = { id: 'g1', name: 'Deniz Kaya', email: 'deniz@example.com' };
  axios.get.mockImplementation(async url => ({ data: url.startsWith('/crm/guest/') ? { guest: profile } : url === '/messaging-center/settings' ? settings : { templates: [] } }));
  axios.post.mockResolvedValue({ data: { success: true, delivery_id: 'delivery' } });
});
afterEach(cleanup);

it('opens a real, contextual offer draft from the route without auto-sending or inventing prices', async () => {
  render(<MemoryRouter initialEntries={['/messaging-dashboard?guest=g1&action=offer']}><MessagingDashboard /></MemoryRouter>);
  expect(await screen.findByText('Deniz Kaya')).toBeInTheDocument();
  expect(screen.getByTestId('send-recipient')).toHaveValue('deniz@example.com');
  expect(screen.getByTestId('send-subject')).toHaveValue('Konaklama teklifiniz');
  expect(screen.getByTestId('send-body')).toHaveValue('');
  expect(screen.getByTestId('send-message-btn')).toBeDisabled();
  expect(screen.getByRole('button', { name: /Ön büroya dön/ })).toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByTestId('send-body'), { target: { value: '1–3 Kasım konaklama teklifiniz; detayları birlikte teyit edelim.' } });
  fireEvent.click(screen.getByTestId('send-message-btn'));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/messaging-center/send', expect.objectContaining({ guest_id: 'g1', recipient: 'deniz@example.com', subject: 'Konaklama teklifiniz', use_case: 'guest_offer' })));
  expect(toast.success).not.toHaveBeenCalledWith(expect.stringContaining('Teslim edildi'));
});

it('never uses a synthetic placeholder address as the recipient', async () => {
  profile = { ...profile, email: 'agency-123@placeholder.local', phone: '' };
  render(<SendTab guestId="g1" offer />);
  expect(await screen.findByText(/Kullanılabilir iletişim bilgisi yok/)).toBeInTheDocument();
  expect(screen.getByTestId('send-recipient')).toHaveValue('');
  expect(screen.getByTestId('send-message-btn')).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('fails closed for a missing/mismatched guest and allows retry without losing identity', async () => {
  profile = { ...profile, id: 'different-person' };
  render(<SendTab guestId="g1" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Misafir bilgileri doğrulanamadı');
  expect(screen.getByTestId('send-recipient')).toBeDisabled();
  profile = { ...profile, id: 'g1' };
  fireEvent.click(screen.getByRole('button', { name: 'Yeniden dene' }));
  await waitFor(() => expect(screen.getByTestId('send-recipient')).toHaveValue('deniz@example.com'));
  expect(axios.get).toHaveBeenLastCalledWith('/crm/guest/g1');
  expect(axios.post).not.toHaveBeenCalled();
});

it('does not present a disabled/unverified provider as a working send action', async () => {
  settings = { email: { ...provider, enabled: false } };
  render(<SendTab guestId="g1" />);
  expect(await screen.findByText(/Devre dışı ·/)).toBeInTheDocument();
  fireEvent.change(screen.getByTestId('send-body'), { target: { value: 'Merhaba' } });
  expect(screen.getByTestId('send-message-btn')).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('clearly distinguishes a sandbox action from real delivery', async () => {
  settings = { email: { ...provider, is_sandbox: true } };
  render(<SendTab guestId="g1" />);
  expect(await screen.findByRole('button', { name: 'Deneme gönderimi yap' })).toBeDisabled();
  await screen.findByText('Deniz Kaya');
  fireEvent.change(screen.getByTestId('send-body'), { target: { value: 'Yalnız yerel test' } });
  fireEvent.click(screen.getByTestId('send-message-btn'));
  await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Gönderim işlemi kaydedildi. Sonucu Gönderim kayıtları sekmesinden izleyebilirsiniz.'));
});

it('surfaces send failure without a false success toast or clearing the draft', async () => {
  axios.post.mockRejectedValue({ response: { data: { detail: 'Gönderim izni bulunamadı' } } });
  render(<SendTab guestId="g1" />);
  await screen.findByText('Deniz Kaya');
  fireEvent.change(screen.getByTestId('send-body'), { target: { value: 'Korunacak taslak' } });
  fireEvent.click(screen.getByTestId('send-message-btn'));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Gönderim izni bulunamadı'));
  expect(toast.success).not.toHaveBeenCalled();
  expect(screen.getByTestId('send-body')).toHaveValue('Korunacak taslak');
});

it('ignores a slow old guest response after the selected guest changes', async () => {
  let resolveOld;
  axios.get.mockImplementation(url => url === '/crm/guest/old' ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve({ data: url === '/crm/guest/g1' ? { guest: profile } : settings }));
  const view = render(<SendTab guestId="old" />);
  view.rerender(<SendTab guestId="g1" />);
  await screen.findByText('Deniz Kaya');
  resolveOld({ data: { guest: { id: 'old', name: 'Eski Kişi', email: 'old@example.com' } } });
  await waitFor(() => expect(screen.getByTestId('send-recipient')).toHaveValue('deniz@example.com'));
  expect(screen.queryByText('Eski Kişi')).not.toBeInTheDocument();
});
