import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CommunicationCenter from '@/components/CommunicationCenter';

vi.mock('@/context/NotificationContext', () => ({
  useNotifications: () => ({ internalUnreadCount: 3, guestRequestsUnreadCount: 2 }),
}));

beforeEach(() => sessionStorage.clear());
afterEach(() => cleanup());

describe('CommunicationCenter', () => {
  it('opens the internal communication destinations from one collapsed launcher', () => {
    render(<CommunicationCenter user={{ id: 'operator', role: 'front_desk' }} />);

    expect(screen.getByRole('button', { name: 'İletişim merkezini aç' })).toBeInTheDocument();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    expect(screen.getByRole('menu', { name: 'İletişim merkezi seçenekleri' })).toBeInTheDocument();
    expect(screen.getByText('Personel mesajları')).toBeInTheDocument();
    expect(screen.getByText('Misafir talepleri')).toBeInTheDocument();
    expect(screen.queryByText('Telefon')).not.toBeInTheDocument();
    expect(screen.getByText('Ekip: 3')).toBeInTheDocument();
    expect(screen.getByText('Misafir: 2')).toBeInTheDocument();
  });

  it('opens unread guest requests from the same launcher', () => {
    const listener = vi.fn();
    window.addEventListener('syroce:open-guest-requests', listener, { once: true });
    render(<CommunicationCenter user={{ id: 'operator', role: 'front_desk' }} />);

    expect(screen.getByTestId('communication-center-launcher')).toHaveTextContent('5');
    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Misafir talepleri/ }));

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('opens messaging through the shared event contract', () => {
    const listener = vi.fn();
    window.addEventListener('syroce:open-internal-chat', listener, { once: true });
    render(<CommunicationCenter user={{ id: 'operator', role: 'front_desk' }} />);

    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Personel mesajları/ }));

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('can be minimized, closed, and restored without losing access', () => {
    render(<CommunicationCenter user={{ id: 'operator', role: 'front_desk' }} />);

    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini küçült' }));

    expect(screen.getByTestId('communication-center-launcher')).toHaveClass('w-12');
    expect(screen.queryByText('İletişim merkezi')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini aç' }));
    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini kapat' }));

    expect(screen.queryByTestId('communication-center-launcher')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'İletişim merkezini göster' }));
    expect(screen.getByTestId('communication-center-launcher')).toHaveClass('w-12');
  });
});
