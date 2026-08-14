import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn(() => new Promise(() => {}));

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'tr' },
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { LiveFeed } from '@/pages/ControlPlane';

describe('ControlPlane live feed', () => {
  it('renders loading placeholders without dereferencing placeholder values', () => {
    const { container } = render(<LiveFeed />);

    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(8);
    expect(screen.queryByText(/Something went wrong/i)).not.toBeInTheDocument();
  });
});
