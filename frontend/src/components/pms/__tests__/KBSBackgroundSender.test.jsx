import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const { command, get } = vi.hoisted(() => ({ command: vi.fn(), get: vi.fn() }));
vi.mock('@/lib/kbsExtensionBridge', () => ({ policeAgentCommand: command }));
vi.mock('axios', () => ({ default: { get } }));
import KBSBackgroundSender from '../KBSBackgroundSender';

describe('KBS police background control', () => {
  let state;
  beforeEach(() => {
    vi.clearAllMocks();
    state = { supported: true, enabled: false, reason: 'not_enabled' };
    command.mockImplementation(async (type, binding) => {
      if (type === 'START') state = { enabled: true, ...binding };
      if (type === 'STOP') state = { enabled: false, reason: 'stopped' };
      return { ok: true, state };
    });
    get.mockResolvedValue({ data: { id: 'user-a', tenant_id: 'hotel-a' } });
  });
  it('does not migrate or enable old auto-send without explicit hotel confirmation', async () => {
    localStorage.setItem('kbs_ext_autosend', '1');
    render(<KBSBackgroundSender tenantId="hotel-a" onOwnershipChange={vi.fn()} />);
    const start = await screen.findByRole('button', { name: 'Arka plan gönderimini etkinleştir' });
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled());
    expect(start).toBeDisabled(); expect(command).not.toHaveBeenCalledWith('START', expect.anything());
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(start);
    await screen.findByRole('button', { name: 'Arka plan gönderimini durdur' });
    expect(command).toHaveBeenCalledWith('START', { tenantId: 'hotel-a', userId: 'user-a', consent: true });
    expect(JSON.stringify(command.mock.calls)).not.toMatch(/password|token|id_number/);
  });
  it('does not enable if the current login no longer belongs to this hotel', async () => {
    get.mockResolvedValue({ data: { id: 'user-a', tenant_id: 'different-hotel' } });
    render(<KBSBackgroundSender tenantId="hotel-a" onOwnershipChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled());
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Arka plan gönderimini etkinleştir' }));
    await screen.findByRole('alert');
    expect(command.mock.calls.some(([type]) => type === 'START')).toBe(false);
  });
  it('reconciles a lost activation response instead of sending another start', async () => {
    command.mockImplementation(async type => {
      if (type === 'START') { state = { enabled: true, tenantId: 'hotel-a' }; return { ok: false, error: 'timeout' }; }
      return { ok: true, state };
    });
    render(<KBSBackgroundSender tenantId="hotel-a" onOwnershipChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled());
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Arka plan gönderimini etkinleştir' }));
    await screen.findByRole('button', { name: 'Arka plan gönderimini durdur' });
    expect(command.mock.calls.filter(([type]) => type === 'START')).toHaveLength(1);
  });
  it('unknown ownership blocks foreground sending; does not pretend the agent is off', async () => {
    command.mockResolvedValue({ ok: false, error: 'timeout' });
    const ownership = vi.fn();
    render(<KBSBackgroundSender tenantId="hotel-a" onOwnershipChange={ownership} />);
    await screen.findByRole('alert');
    expect(ownership).toHaveBeenLastCalledWith(true);
    expect(screen.getByRole('button', { name: 'Arka plan gönderimini etkinleştir' })).toBeDisabled();
  });

  it('an older status response cannot undo a reconciled activation', async () => {
    let count = 0, release;
    command.mockImplementation(async type => {
      if (type === 'START') state = { enabled: true, tenantId: 'hotel-a' };
      if (type === 'STATUS' && ++count === 2) return new Promise(resolve => { release = resolve; });
      return { ok: true, state };
    });
    const ownership = vi.fn();
    render(<KBSBackgroundSender tenantId="hotel-a" onOwnershipChange={ownership} />);
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Gönderici durumunu yenile' }));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Arka plan gönderimini etkinleştir' }));
    await screen.findByRole('button', { name: 'Arka plan gönderimini durdur' });
    await act(async () => release({ ok: true, state: { enabled: false } }));
    expect(screen.getByRole('button', { name: 'Arka plan gönderimini durdur' })).toBeInTheDocument();
    expect(ownership).toHaveBeenLastCalledWith(true);
  });
  it('another hotel must be stopped, and Jandarma view cannot start a police agent', async () => {
    state = { enabled: true, tenantId: 'hotel-b' };
    const { rerender } = render(<KBSBackgroundSender tenantId="hotel-a" onOwnershipChange={vi.fn()} />);
    const stop = await screen.findByRole('button', { name: 'Arka plan gönderimini durdur' });
    expect(screen.getByRole('alert')).toHaveTextContent('Başka bir otel');
    fireEvent.click(stop);
    await screen.findByRole('button', { name: 'Arka plan gönderimini etkinleştir' });
    rerender(<KBSBackgroundSender tenantId="hotel-a" allowStart={false} onOwnershipChange={vi.fn()} />);
    await waitFor(() => expect(screen.queryByRole('checkbox')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Arka plan gönderimini etkinleştir' })).not.toBeInTheDocument();
  });
});
