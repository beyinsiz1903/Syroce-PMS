import { lazy } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ProtectedRoute } from '../ProtectedRoute';

vi.mock('@/components/Layout', () => ({
  default: ({ children }) => <div data-testid="outer-layout">{children}</div>,
}));

function LegacyLayoutAwarePage({ embedded = false }) {
  return embedded
    ? <div data-testid="page">content</div>
    : <div data-testid="inner-layout"><div data-testid="page">content</div></div>;
}

describe('ProtectedRoute layout ownership', () => {
  it('marks wrapped pages as embedded to prevent duplicate application chrome', async () => {
    render(
      <MemoryRouter>
        <ProtectedRoute
          isAuthenticated
          wrapLayout
          element={<LegacyLayoutAwarePage />}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('outer-layout')).toBeInTheDocument();
    expect(screen.getByTestId('page')).toBeInTheDocument();
    expect(screen.queryByTestId('inner-layout')).not.toBeInTheDocument();
  });

  it('keeps application chrome visible while a lazy page is loading', async () => {
    const PendingPage = lazy(() => new Promise(() => {}));

    render(
      <MemoryRouter>
        <ProtectedRoute
          isAuthenticated
          wrapLayout
          element={<PendingPage />}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('outer-layout')).toBeInTheDocument();
    expect(screen.getByTestId('route-content-loading')).toHaveTextContent('Sayfa hazırlanıyor');
  });
});
