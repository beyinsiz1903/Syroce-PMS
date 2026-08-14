import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(() => new Promise(() => {})),
    post: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import ModuleStorePage from '@/pages/ModuleStorePage';

describe('ModuleStorePage loading state', () => {
  it('renders its skeleton cards without dereferencing empty placeholder values', () => {
    const { container } = render(
      <MemoryRouter>
        <ModuleStorePage user={{}} tenant={{}} onLogout={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: /modul_pazari/ })).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });
});
