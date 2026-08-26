import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cacheTenantScope,
  clearAxiosCache,
  installAxiosCache,
  stableSerialize,
} from "@/lib/axios-cache";

function createClient(adapter) {
  return {
    defaults: { adapter },
    interceptors: { response: { use: vi.fn() } },
  };
}

describe("axios GET dedupe cache", () => {
  beforeEach(() => {
    clearAxiosCache();
    localStorage.clear();
    localStorage.setItem("tenant", JSON.stringify({ id: "tenant-a" }));
    localStorage.setItem("user", JSON.stringify({ id: "user-a" }));
  });

  it("stable-serializes params regardless of object key order", () => {
    expect(stableSerialize({ b: 2, a: 1 })).toBe(stableSerialize({ a: 1, b: 2 }));
  });

  it("coalesces parallel equivalent GETs and serves the micro-cache", async () => {
    const adapter = vi.fn().mockResolvedValue({ status: 200, data: { ok: true }, headers: {} });
    const client = createClient(adapter);
    installAxiosCache(client);

    const first = client.defaults.adapter({ method: "get", url: "/spa/services", params: { b: 2, a: 1 } });
    const second = client.defaults.adapter({ method: "get", url: "/spa/services", params: { a: 1, b: 2 } });
    const [, shared] = await Promise.all([first, second]);
    const cached = await client.defaults.adapter({ method: "get", url: "/spa/services", params: { a: 1, b: 2 } });

    expect(adapter).toHaveBeenCalledTimes(1);
    expect(shared.cached).toBe(true);
    expect(cached.cached).toBe(true);
  });

  it("isolates cache keys by tenant in cookie-auth sessions", async () => {
    const adapter = vi.fn().mockResolvedValue({ status: 200, data: {}, headers: {} });
    const client = createClient(adapter);
    installAxiosCache(client);

    await client.defaults.adapter({ method: "get", url: "/rms/dashboard-kpis" });
    localStorage.setItem("tenant", JSON.stringify({ id: "tenant-b" }));
    await client.defaults.adapter({ method: "get", url: "/rms/dashboard-kpis" });

    expect(cacheTenantScope()).toBe("tenant:tenant-b|user:user-a");
    expect(adapter).toHaveBeenCalledTimes(2);
  });

  it("keeps retry metadata isolated for coalesced failed callers", async () => {
    const adapter = vi.fn((config) => Promise.reject(Object.assign(new Error("throttled"), {
      config,
      response: { status: 429, headers: { "retry-after": "1" } },
    })));
    const client = createClient(adapter);
    installAxiosCache(client);
    const firstConfig = { method: "get", url: "/mice/diary", params: { month: 8 } };
    const secondConfig = { method: "get", url: "/mice/diary", params: { month: 8 } };

    const [first, second] = await Promise.allSettled([
      client.defaults.adapter(firstConfig),
      client.defaults.adapter(secondConfig),
    ]);

    expect(adapter).toHaveBeenCalledTimes(1);
    expect(first.reason.config).toBe(firstConfig);
    expect(second.reason.config).toBe(secondConfig);
    expect(first.reason).not.toBe(second.reason);
  });
});
