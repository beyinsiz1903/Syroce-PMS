import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import FloatingActionButton from '@/components/FloatingActionButton';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: () => 'Hizli Islemler' }),
}));

afterEach(() => cleanup());

describe('FloatingActionButton', () => {
  it('renders component icons without crashing when the menu opens', () => {
    const ActionIcon = (props) => <svg data-testid="action-icon" {...props} />;

    render(
      <FloatingActionButton
        actions={[
          {
            label: 'Yeni Rezervasyon',
            icon: ActionIcon,
            onClick: vi.fn(),
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByTitle('Hizli Islemler'));

    expect(screen.getByTestId('action-icon')).toBeInTheDocument();
    expect(screen.getByTitle('Yeni Rezervasyon')).toBeInTheDocument();
  });

  it('runs the selected action once and closes the menu', () => {
    const onClick = vi.fn();
    const ActionIcon = (props) => <svg data-testid="action-icon" {...props} />;

    render(
      <FloatingActionButton
        actions={[
          {
            label: 'Yeni Misafir',
            icon: ActionIcon,
            onClick,
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByTitle('Hizli Islemler'));
    fireEvent.click(screen.getByTitle('Yeni Misafir'));

    expect(onClick).toHaveBeenCalledOnce();
    expect(screen.queryByTitle('Yeni Misafir')).not.toBeInTheDocument();
  });
});
