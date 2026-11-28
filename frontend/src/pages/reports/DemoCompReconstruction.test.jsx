import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import axios from 'axios';
import DemoCompReconstruction from './DemoCompReconstruction';
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const sources = ['cacc4ae5-bd21-55cf-bddb-d975d9ff6ba3', 'fd2a768f-fc39-495b-ae63-716281a43116'].map(id => ({ id }));
const plan = { notice: 'Yeni sentetik test tanımı; özgün tarihî vergi doğrulanmış değildir.', source_fingerprint: 'a'.repeat(64), documents: [] };
const open = async () => {
  fireEvent.click(screen.getByRole('button', { name: /incele/ }));
  await screen.findByText(plan.notice);
};
describe('controlled synthetic comp repair', () => {
  beforeEach(() => { vi.clearAllMocks(); axios.get.mockResolvedValue({ data: plan }); });
  it('requires explicit acknowledgement and reason and retains request identity after uncertain response', async () => {
    const applied = vi.fn();
    axios.post.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: { ...plan, applied: true } });
    render(<DemoCompReconstruction sources={sources} onApplied={applied} />);
    await open();
    const save = screen.getByRole('button', { name: /kaydet/ });
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Kullanıcı onaylı sentetik düzeltme; tarihî vergi doğrulanmadı.' } });
    expect(save.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(save);
    await screen.findByRole('alert');
    expect(applied).not.toHaveBeenCalled();
    fireEvent.click(save);
    await screen.findByRole('status');
    expect(axios.post.mock.calls[0][1]).toEqual(axios.post.mock.calls[1][1]);
    expect(axios.post.mock.calls[0][1].confirmation).toBe('DEFINE_SYNTHETIC_COMP_25_60_ONLY');
    expect(applied).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: /kaydet/ })).toBeNull();
  });
  it('hides repair for unrelated sources', () => {
    render(<DemoCompReconstruction sources={[sources[0]]} />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
  });
  it('displays permission refusal without writing', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Yetkiniz yok' } } });
    render(<DemoCompReconstruction sources={sources} />);
    fireEvent.click(screen.getByRole('button'));
    expect((await screen.findByRole('alert')).textContent).toBe('Yetkiniz yok');
    expect(axios.post).not.toHaveBeenCalled();
  });
  it('reconciles an existing receipt without a second write', async () => {
    axios.get.mockResolvedValue({ data: { ...plan, already_applied: true } });
    render(<DemoCompReconstruction corrected={[{ id: sources[0].id }]} />);
    await open();
    await screen.findByRole('status');
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });
});
