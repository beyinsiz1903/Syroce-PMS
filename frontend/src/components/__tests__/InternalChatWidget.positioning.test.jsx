import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import InternalChatWidget from '@/components/InternalChatWidget';

vi.mock('@/context/NotificationContext', () => ({
  useNotifications: () => ({ internalUnreadCount: 0, guestRequestsUnreadCount: 0 }),
}));

vi.mock('@/components/pms/InternalChatTab', () => ({
  default: () => <div>Mesajlar</div>,
}));

afterEach(() => cleanup());

describe('InternalChatWidget positioning', () => {
  it('keeps the launcher above fixed page action bars', () => {
    render(<InternalChatWidget user={{ id: 'operator' }} />);

    expect(screen.getByRole('button', { name: 'Personel mesajlaşmasını aç' })).toHaveClass(
      'safe-fixed-bottom-fab',
    );
  });

  it('keeps the open panel above its raised launcher', () => {
    render(<InternalChatWidget user={{ id: 'operator' }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Personel mesajlaşmasını aç' }));

    expect(screen.getByRole('dialog', { name: 'Personel Mesajlaşması' })).toHaveClass(
      'safe-fixed-bottom-chat',
    );
  });

  it('opens the guest-request workspace with its own accessible title', () => {
    render(<InternalChatWidget user={{ id: 'operator' }} hideLauncher />);

    fireEvent(window, new CustomEvent('syroce:open-guest-requests'));

    expect(screen.getByRole('dialog', { name: 'Misafir Talepleri' })).toBeInTheDocument();
  });
});
