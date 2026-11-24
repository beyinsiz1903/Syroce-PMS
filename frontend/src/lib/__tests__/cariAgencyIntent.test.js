import { beforeEach, describe, expect, it, vi } from 'vitest';
import { submitCariAgencyIntent } from '../cariAgencyIntent';
const payload = { amount: 25, cari_account_id: 'agency', description: 'Alacak devri' };
beforeEach(() => sessionStorage.clear());
describe('cari agency durable intent', () => {
  it('reuses the UUID after an ambiguous network result and clears only after success', async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({ success: true });
    await expect(submitCariAgencyIntent('t', 'company', payload, send)).rejects.toThrow('timeout');
    await submitCariAgencyIntent('t', 'company', payload, send);
    expect(send.mock.calls[0][0].request_id).toBe(send.mock.calls[1][0].request_id);
    expect(sessionStorage.length).toBe(0);
  });
  it('prevents changed form submission while the previous result is uncertain', async () => {
    const send = vi.fn().mockRejectedValue(new Error('timeout'));
    await expect(submitCariAgencyIntent('t', 'company', payload, send)).rejects.toThrow();
    await expect(submitCariAgencyIntent('t', 'company', { ...payload, amount: 26 }, send)).rejects.toThrow('belirsiz');
    expect(send).toHaveBeenCalledTimes(1);
  });
  it('keeps tenant intent scopes separate and requires tenant identity', async () => {
    const send = vi.fn().mockRejectedValue(new Error('timeout'));
    await expect(submitCariAgencyIntent('', 'company', payload, send)).rejects.toThrow('tesis');
    expect(send).not.toHaveBeenCalled();
    await expect(submitCariAgencyIntent('a', 'company', payload, send)).rejects.toThrow();
    await expect(submitCariAgencyIntent('b', 'company', payload, send)).rejects.toThrow();
    expect(send.mock.calls[0][0].request_id).not.toBe(send.mock.calls[1][0].request_id);
  });
  it('forgets a pre-write validation failure but retains an ambiguous409', async () => {
    const send = vi.fn().mockRejectedValueOnce({ response: { status: 422 } }).mockRejectedValueOnce({ response: { status: 409 } });
    await expect(submitCariAgencyIntent('t', 'company', payload, send)).rejects.toBeDefined();
    expect(sessionStorage.length).toBe(0);
    await expect(submitCariAgencyIntent('t', 'company', payload, send)).rejects.toBeDefined();
    expect(sessionStorage.length).toBe(1);
  });
  it('does not send when durable storage fails', async () => {
    vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: () => { throw new Error('storage denied'); } });
    const send = vi.fn();
    await expect(submitCariAgencyIntent('t', 'company', payload, send)).rejects.toThrow('storage denied');
    expect(send).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
