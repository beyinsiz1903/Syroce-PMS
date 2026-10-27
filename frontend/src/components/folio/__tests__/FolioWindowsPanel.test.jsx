import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  it('refreshes balances after allocation and ignores the late response from an older revision', async () => {
    let oldResponse;
    get.mockImplementationOnce(() => new Promise(resolve => { oldResponse = resolve; }));
    const row = { folio_id: 'company', folio_number: 'F-2', window_number: 2, payor_type: 'company', status: 'open', currency: 'TRY', charges_count: 1, balance: 6000 };
    const page = render(<FolioWindowsPanel bookingId="b" revision={0} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    get.mockResolvedValueOnce({ data: [row] });
    page.rerender(<FolioWindowsPanel bookingId="b" revision={1} />);
    expect(await screen.findByTestId('window-row-2')).toHaveTextContent('6.000');
    await act(async () => oldResponse({ data: [{ ...row, balance: 0 }] }));
    expect(screen.getByTestId('window-row-2')).toHaveTextContent('6.000');
  });

  it('does not keep stale balances selectable when refresh fails', async () => {
    get.mockResolvedValueOnce({ data: [{ folio_id: 'guest', folio_number: 'F-1', window_number: 1, status: 'open', balance: 100 }] });
    const page = render(<FolioWindowsPanel bookingId="b" onSelect={vi.fn()} revision={0} />);
    await screen.findByTestId('window-row-1');
    get.mockRejectedValueOnce(new Error('offline'));
    page.rerender(<FolioWindowsPanel bookingId="b" onSelect={vi.fn()} revision={1} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Folyo hesapları alınamadı');
    expect(screen.queryByRole('button', { name: 'Bu folyoyu seç' })).not.toBeInTheDocument();
  });
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

  it('allows read-only selection of a historical folio without exposing payer mutations', async () => {
    get.mockResolvedValueOnce({ data: [{ folio_id: 'closed', folio_number: 'F-OLD', window_number: 1, status: 'closed', balance: 0, folio_type: 'guest' }] });
    const onSelect = vi.fn();
    render(<FolioWindowsPanel bookingId="b" readOnly onSelect={onSelect} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Bu folyoyu seç' }));
    expect(onSelect).toHaveBeenCalledWith('closed');
    expect(screen.queryByRole('button', { name: 'Ödeyeni düzenle' })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('does not expose mutation buttons in a read-only reservation', async () => {
    render(<FolioWindowsPanel bookingId="b" readOnly />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.queryByTestId('window-add-btn')).not.toBeInTheDocument();
  });
});
