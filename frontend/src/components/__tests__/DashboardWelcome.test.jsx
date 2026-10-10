import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DashboardWelcome from '../experience/DashboardWelcome';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: key => key === 'dashboard.welcome' ? 'Hoş geldiniz' : key }),
}));
afterEach(cleanup);

describe('DashboardWelcome', () => {
  it('keeps one accessible heading with a lighter greeting and emphasized dynamic name', () => {
    render(<DashboardWelcome user={{ name: 'Ömer Biliş' }} tenant={{ property_name: 'Örnek Otel' }} />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Hoş geldiniz, Ömer Biliş');
    expect(screen.getByText('Ömer Biliş')).toHaveClass('font-semibold');
    expect(screen.getByText('Hoş geldiniz,')).toHaveClass('text-muted-foreground');
    expect(screen.getByText('Örnek Otel')).toBeVisible();
  });
  it('handles missing data without rendering a dangling comma', () => {
    render(<DashboardWelcome />);
    expect(screen.getByRole('heading')).toHaveTextContent(/^Hoş geldiniz$/);
  });
  it('renders long and non-Latin names as text, not markup', () => {
    const name = 'Ömer Biliş 長い名前 <script>alert(1)</script>';
    render(<DashboardWelcome user={{ name }} />);
    expect(screen.getByText(name)).toBeVisible();
    expect(document.querySelector('script')).toBeNull();
  });
});
