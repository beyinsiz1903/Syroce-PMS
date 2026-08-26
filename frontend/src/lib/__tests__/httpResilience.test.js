import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  installAxiosResilience,
  parseRetryAfter,
  retryDelayMs,
  shouldRetryRequest,
} from "@/lib/httpResilience";

function createClient() {
  const rejectedHandlers = [];
  return {
    rejectedHandlers,
    request: vi.fn().mockResolvedValue({ data: { ok: true } }),
    interceptors: {
      response: {
        use: vi.fn((_, rejected) => rejectedHandlers.push(rejected)),
      },
    },
  };
}

describe("httpResilience", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("parses Retry-After seconds and HTTP dates", () => {
    const now = Date.parse("2026-08-26T08:00:00Z");
    expect(parseRetryAfter("3", now)).toBe(3000);
    expect(parseRetryAfter("Wed, 26 Aug 2026 08:00:05 GMT", now)).toBe(5000);
    expect(parseRetryAfter("invalid", now)).toBeNull();
  });

  it("uses Retry-After ahead of exponential backoff", () => {
    const error = { response: { headers: { "retry-after": "4" } } };
    expect(retryDelayMs(error, 2, { random: () => 0 })).toBe(4000);
  });

  it("retries safe transient reads but never mutations", () => {
    expect(shouldRetryRequest({ config: { method: "get" }, response: { status: 429 } })).toBe(true);
    expect(shouldRetryRequest({ config: { method: "post" }, response: { status: 503 } })).toBe(false);
    expect(shouldRetryRequest({ config: { method: "get" }, response: { status: 422 } })).toBe(false);
  });

  it("waits for Retry-After and retries through the same client", async () => {
    const client = createClient();
    const sleep = vi.fn().mockResolvedValue(undefined);
    installAxiosResilience(client, { sleep, random: () => 0, reportFailure: vi.fn() });

    const config = { method: "get", url: "/mice/diary" };
    const error = {
      config,
      response: { status: 429, headers: { "retry-after": "2" } },
    };
    await client.rejectedHandlers[0](error);

    expect(sleep).toHaveBeenCalledWith(2000);
    expect(config._syroceRetryCount).toBe(1);
    expect(client.request).toHaveBeenCalledWith(config);
  });

  it("reports a final module read failure once retries are exhausted", async () => {
    const client = createClient();
    const reportFailure = vi.fn();
    installAxiosResilience(client, { defaultRetries: 0, reportFailure });
    const error = {
      config: { method: "get", url: "/hr/staff" },
      response: { status: 503, headers: {} },
    };

    await expect(client.rejectedHandlers[0](error)).rejects.toBe(error);
    expect(reportFailure).toHaveBeenCalledTimes(1);
    expect(error.config._syroceFailureReported).toBe(true);
  });
});
