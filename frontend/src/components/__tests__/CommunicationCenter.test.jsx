import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CommunicationCenter from '@/components/CommunicationCenter';

vi.mock('@/context/NotificationContext', () => ({
  useNotifications: () => ({ internalUnreadCount: 3 }),
}));

afterEach(() => cleanup());

describe('CommunicationCenter', () => {
  it('combines messaging and phone into one collapsed launcher', () => {
    render(<CommunicationCenter user={{ id: 'operator', role: 'front_desk' }} />);

    expect(screen.getByRole('button', { name: 'İletişim merkezini aç' })).toBeInTheDocument();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    expect(screen.getByRole('menu', { name: 'İletişim merkezi seçenekleri' })).toBeInTheDocument();
    expect(screen.getByText('Personel mesajları')).toBeInTheDocument();
    expect(screen.getByText('Telefon')).toBeInTheDocument();
  });

  it('opens messaging through the shared event contract', () => {
    const listener = vi.fn();
    window.addEventListener('syroce:open-internal-chat', listener, { once: true });
    render(<CommunicationCenter user={{ id: 'operator', role: 'front_desk' }} />);

    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Personel mesajları/ }));

    expect(listener).toHaveBeenCalledTimes(1);
  });
});

