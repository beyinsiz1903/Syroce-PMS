import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { create: () => ({ post, interceptors: { request: { use: vi.fn() } } }) } }));
import AgencyRecover from '../AgencyRecover';
afterEach(() => { cleanup(); vi.clearAllMocks(); window.history.replaceState({}, '', '/'); });

it('requests recovery with normalized email and displays generic response', async () => {
  post.mockResolvedValue({ data: { message: 'Uygun hesap varsa bağlantı gönderilecektir.' } });
  render(<MemoryRouter><AgencyRecover /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Acente hesabı e-posta adresi'), { target: { value: 'Agent@Example.com' } });
  fireEvent.click(screen.getByRole('button', { name: 'Yenileme bağlantısı gönder' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/marketplace/v1/extranet/auth/recover', { email: 'agent@example.com' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Uygun hesap');
});

it('removes token from address and submits matching strong passwords', async () => {
  window.history.replaceState({}, '', '/agency-recover#token=secret');
  post.mockResolvedValue({ data: { ok: true } });
  render(<MemoryRouter><AgencyRecover /></MemoryRouter>);
  expect(window.location.hash).toBe('');
  fireEvent.change(screen.getByLabelText('Yeni şifre'), { target: { value: 'SecureAgency2026!' } });
  fireEvent.change(screen.getByLabelText('Yeni şifre tekrar'), { target: { value: 'SecureAgency2026!' } });
  fireEvent.click(screen.getByRole('button', { name: 'Şifreyi yenile' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/marketplace/v1/extranet/auth/reset', { token: 'secret', password: 'SecureAgency2026!' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Şifreniz yenilendi');
});
