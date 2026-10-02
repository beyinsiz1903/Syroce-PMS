import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AppLauncher from '../AppLauncher';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_key, fallback) => fallback }) }));

describe('AppLauncher accessibility', () => {
  it('gives the icon-only launcher an accessible name and visible focus style', () => {
    render(<AppLauncher user={{ role: 'super_admin' }} />);

    const launcher = screen.getByRole('button', { name: 'Uygulama seçiciyi aç' });
    expect(launcher).toHaveAttribute('title', 'Uygulamalar');
    expect(launcher.className).toContain('focus-visible:ring-2');
  });

  it('does not expose the launcher to a non-superadmin user', () => {
    const { container } = render(<AppLauncher user={{ role: 'admin' }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
