import { describe, expect, it, vi } from 'vitest';
import {
  isTransientLoginGatewayError,
  postLoginWithGatewayRetry,
} from '@/lib/authLoginResilience';

describe('authLoginResilience', () => {
  it.each([502, 503, 504])('retries a transient %s login response once', async (status) => {
    const response = { data: { access_token: 'token' } };
    const client = {
      post: vi.fn()
        .mockRejectedValueOnce({ response: { status } })
        .mockResolvedValueOnce(response),
    };
    const sleep = vi.fn().mockResolvedValue(undefined);

    await expect(postLoginWithGatewayRetry(client, { email: 'qa@example.com' }, { sleep }))
      .resolves.toBe(response);
    expect(client.post).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(600);
  });

  it('does not retry credential errors', async () => {
    const error = { response: { status: 401 } };
    const client = { post: vi.fn().mockRejectedValue(error) };
    const sleep = vi.fn();

    await expect(postLoginWithGatewayRetry(client, {}, { sleep })).rejects.toBe(error);
    expect(client.post).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it('recognizes only transient gateway responses', () => {
    expect(isTransientLoginGatewayError({ response: { status: 504 } })).toBe(true);
    expect(isTransientLoginGatewayError({ response: { status: 429 } })).toBe(false);
    expect(isTransientLoginGatewayError({})).toBe(false);
  });
});
