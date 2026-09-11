import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import ModuleScopeBoundary from '@/routes/ModuleScopeBoundary';

describe('ModuleScopeBoundary', () => {
  it('explains unavailable access instead of silently redirecting to dashboard', () => {
    render(
      <MemoryRouter>
        <ModuleScopeBoundary user={{ module_scopes: [] }} scopes={['sales']}>
          <div>Satış modülü</div>
        </ModuleScopeBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Kurulum gerekli' })).toBeInTheDocument();
    expect(screen.getByText('Bu modül tesisinizde etkin değil. Paketinizi veya kullanıcı yetkinizi kontrol edin.')).toBeInTheDocument();
    expect(screen.queryByText('Satış modülü')).not.toBeInTheDocument();
  });

  it('renders the module when one requested scope is available', () => {
    render(
      <MemoryRouter>
        <ModuleScopeBoundary user={{ module_scopes: ['sales'] }} scopes={['sales']}>
          <div>Satış modülü</div>
        </ModuleScopeBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText('Satış modülü')).toBeInTheDocument();
  });

  it('does not show the setup screen to a super-admin represented by roles', () => {
    render(
      <MemoryRouter>
        <ModuleScopeBoundary user={{ role: 'operator', roles: ['super_admin'], module_scopes: [] }} scopes={['frontdesk']}>
          <div>Rezervasyon takvimi</div>
        </ModuleScopeBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText('Rezervasyon takvimi')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Kurulum gerekli' })).not.toBeInTheDocument();
  });
});
