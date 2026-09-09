import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const { post, navigate } = vi.hoisted(() => ({ post: vi.fn(), navigate: vi.fn() }));

vi.mock('axios', () => ({ default: { post } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('react-router-dom', () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  useNavigate: () => navigate,
}));

import SupplierAuthPage from '@/pages/SupplierAuthPage';

describe('SupplierAuthPage', () => {
  beforeEach(() => {
    post.mockReset();
    navigate.mockReset();
    localStorage.clear();
  });

  it('authenticates against the real vendor endpoint and opens the vendor portal', async () => {
    post.mockResolvedValue({ data: { access_token: 'vendor-jwt', vendor: { id: 'v-1' } } });
    render(<SupplierAuthPage />);

    fireEvent.change(screen.getByLabelText('cm.pages_SupplierAuthPage.e_posta'), { target: { value: 'vendor@example.com' } });
    fireEvent.change(screen.getByLabelText('cm.pages_SupplierAuthPage.parola'), { target: { value: 'safe-password' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Giriş Yap' }).at(-1));

    await waitFor(() => expect(post).toHaveBeenCalledWith('/supplies-market/vendor/login', {
      email: 'vendor@example.com',
      password: 'safe-password',
    }));
    expect(localStorage.getItem('vendor_token')).toBe('vendor-jwt');
    expect(navigate).toHaveBeenCalledWith('/vendor', { replace: true });
    expect(screen.queryByText('Demo modu')).not.toBeInTheDocument();
  });

  it('shows the backend authentication error without creating a session', async () => {
    post.mockRejectedValue({ response: { status: 401, data: { detail: 'E-posta veya şifre hatalı' } } });
    render(<SupplierAuthPage />);

    fireEvent.change(screen.getByLabelText('cm.pages_SupplierAuthPage.e_posta'), { target: { value: 'bad@example.com' } });
    fireEvent.change(screen.getByLabelText('cm.pages_SupplierAuthPage.parola'), { target: { value: 'wrong-password' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Giriş Yap' }).at(-1));

    expect(await screen.findByText('E-posta veya şifre hatalı')).toBeInTheDocument();
    expect(localStorage.getItem('vendor_token')).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });
});
