import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import NotAvailable from '@/pages/NotAvailable';

describe('NotAvailable', () => {
  it('shows recovery guidance without exposing role diagnostics', () => {
    render(
      <MemoryRouter>
        <NotAvailable />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading')).toHaveTextContent('Bu sayfa planınıza dahil değil');
    expect(screen.queryByText(/DEBUG:|userRole=|userRoles=/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Geri' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Panele Git' })).toBeInTheDocument();
  });
});
