import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DemoSourceNotice from '../DemoSourceNotice';

const { fetchJson } = vi.hoisted(() => ({ fetchJson: vi.fn() }));
vi.mock('@/lib/fetchRetry', () => ({ fetchJsonWithRetry: fetchJson }));
const DEMO = { id: '5bad4a34-6ee3-4566-9053-741b7375a9cf' };

beforeEach(() => { fetchJson.mockReset(); });

describe('Demo reconstruction disclosure', () => {
  it('never calls a demo endpoint or adds a notice for another hotel', () => {
    render(<DemoSourceNotice tenant={{ id: 'real-hotel' }} />);
    expect(fetchJson).not.toHaveBeenCalled();
    expect(screen.queryByRole('note')).toBeNull();
  });
  it('keeps the warning visible on a failed status read and in print', async () => {
    fetchJson.mockRejectedValue(new Error('unavailable'));
    render(<DemoSourceNotice tenant={DEMO} />);
    await act(async () => {});
    expect(screen.getByRole('note')).toHaveTextContent('gerçek mali doğrulama değildir');
    expect(screen.getByRole('note').className).not.toContain('print:hidden');
  });
  it('shows reconstruction and historical integrity limits without claiming the old chain passed', async () => {
    fetchJson.mockResolvedValue({ applied: true, policy_id: 'demo-policy', result: { document_count: 43, cashier_appended: 6 } });
    render(<DemoSourceNotice tenant={DEMO} />);
    expect(await screen.findByText(/43 kaynak/)).toBeInTheDocument();
    expect(screen.getByText(/69 tarihî/)).toHaveTextContent("Güncel zincir durumunu Denetim Merkezi'nden doğrulayın");
    expect(fetchJson).toHaveBeenCalledExactlyOnceWith('/api/pms/demo-source-remediation/status', { credentials: 'include' });
  });
  it('does not leak the last demo status when switching tenants', async () => {
    let resolve;
    fetchJson.mockReturnValue(new Promise(done => { resolve = done; }));
    const page = render(<DemoSourceNotice tenant={DEMO} />);
    page.rerender(<DemoSourceNotice tenant={{ id: 'other' }} />);
    await act(async () => { resolve({ applied: true, result: { document_count: 43 } }); });
    expect(screen.queryByRole('note')).toBeNull();
  });
});
