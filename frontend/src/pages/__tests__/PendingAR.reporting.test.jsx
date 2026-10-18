import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import PendingAR from '../PendingAR';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

describe('Pending AR reporting safety', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('downloads company aging through the authenticated client, not a new unauthorized tab', async () => {
    const blob = new Blob(['PK-test'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    axios.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/excel') ? blob : url === '/folio/pending-ar' ? [] : {} }));
    const createObjectURL = vi.fn(() => 'blob:aging-test');
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = vi.fn(); });
    const click = vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<PendingAR />);
    fireEvent.click(await screen.findByRole('button', { name: "Yaşlandırmayı Excel'e Aktar" }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/reports/company-aging/excel', { responseType: 'blob' }));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledOnce();
  });

  it('never recomputes incomplete debt after the ledger request fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockImplementation(url => url === '/folio/pending-ar' ? Promise.reject(new Error('denied')) : Promise.resolve({ data: {} }));
    render(<PendingAR />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Alacak bakiyeleri doğrulanamadı');
    expect(screen.getByText('Alınamadı')).toBeInTheDocument();
    expect(axios.get).not.toHaveBeenCalledWith('/companies');
  });
});
