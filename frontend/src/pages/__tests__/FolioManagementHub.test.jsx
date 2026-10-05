import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FolioManagementHub from '../FolioManagementHub';

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

describe('FolioManagementHub', () => {
  beforeEach(() => navigate.mockClear());

  it('connects every folio task to its working workspace', () => {
    render(<FolioManagementHub />);

    for (const [button, path] of [
      ['Folyoları aç', '/app/pms?tab=cashier'],
      ['Kuralları yönet', '/folio-routing'],
      ['Grup folyolarını aç', '/group-folio'],
      ['Faturaları aç', '/app/invoices'],
    ]) {
      fireEvent.click(screen.getByRole('button', { name: new RegExp(button) }));
      expect(navigate).toHaveBeenLastCalledWith(path);
    }
  });
});
