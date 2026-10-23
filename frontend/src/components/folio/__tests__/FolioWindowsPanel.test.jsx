import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FolioWindowsPanel from '../FolioWindowsPanel';

const { get, post, patch } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post, patch } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
beforeEach(() => {
  get.mockReset().mockImplementation(async url => ({ data: url.includes('cari-accounts') ? { accounts: [{ id: 'ar', name: 'Örnek Şirket' }] } : [] }));
  post.mockReset().mockResolvedValue({}); patch.mockReset().mockResolvedValue({});
});

describe('folio payee binding', () => {
  it('requires and sends a real AR account for company folios', async () => {
    const onChanged = vi.fn();
    render(<FolioWindowsPanel bookingId="b" onChanged={onChanged} />);
    fireEvent.click(screen.getByTestId('window-add-btn'));
    fireEvent.change(screen.getByLabelText('Folyo ödeyen türü'), { target: { value: 'company' } });
    expect(screen.getByRole('button', { name: 'Aç' })).toBeDisabled();
    await screen.findByRole('option', { name: 'Örnek Şirket' });
    fireEvent.change(screen.getByLabelText('Folyo cari hesabı'), { target: { value: 'ar' } });
    fireEvent.click(screen.getByRole('button', { name: 'Aç' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/folio-windows', { booking_id: 'b', payor_type: 'company', cari_account_id: 'ar' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('does not expose mutation buttons in a read-only reservation', async () => {
    render(<FolioWindowsPanel bookingId="b" readOnly />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByTestId('window-add-btn')).not.toBeInTheDocument();
  });
});
