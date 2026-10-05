import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import UserProfileDialog from '../UserProfileDialog';

vi.mock('axios', () => ({ default: { patch: vi.fn() } }));

describe('UserProfileDialog', () => {
  beforeEach(() => {
    axios.patch.mockReset();
    axios.patch.mockResolvedValue({ data: { success: true } });
  });

  it('updates the login email and refreshes the tenant list', async () => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(<UserProfileDialog
      target={{ id: 'zeliha', name: 'Zeliha', email: 'zeliha@thecaanyonkartepe.com' }}
      onClose={onClose}
      onSaved={onSaved}
    />);
    fireEvent.change(screen.getByLabelText('E-posta'), { target: { value: 'ZELIHA@THECANYONKARTEPE.COM' } });
    fireEvent.click(screen.getByRole('button', { name: 'Bilgileri Kaydet' }));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith('/admin/users/zeliha/profile', {
      name: 'Zeliha',
      email: 'zeliha@thecanyonkartepe.com',
    }));
    expect(onSaved).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
