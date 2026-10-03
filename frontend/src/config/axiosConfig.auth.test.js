import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requestUse: vi.fn(),
  responseUse: vi.fn(),
  adapter: vi.fn(),
}));

vi.mock("axios", () => ({
  default: {
    defaults: {
      baseURL: "",
      timeout: 0,
      withCredentials: false,
      headers: { common: {} },
      adapter: mocks.adapter,
    },
    getAdapter: vi.fn((adapter) => adapter),
    interceptors: {
      request: { use: mocks.requestUse },
      response: { use: mocks.responseUse },
    },
  },
}));

describe("axios auth header migration", () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.requestUse.mockClear();
    mocks.responseUse.mockClear();
  });

  it("never replaces a refreshed Authorization header with a stale legacy token", async () => {
    // Importing after clearing the modules makes the request interceptor
    // registration observable and keeps this test independent from app boot.
    await vi.resetModules();
    await import("./axiosConfig");

    localStorage.setItem("token", "legacy-expired-token");
    const requestInterceptor = mocks.requestUse.mock.calls.at(-1)[0];
    const config = requestInterceptor({
      url: "/auth/me",
      method: "get",
      headers: { Authorization: "Bearer refreshed-access-token" },
    });

    expect(config.headers.Authorization).toBe("Bearer refreshed-access-token");
  });

  it("uses a legacy token only when a request has no explicit Authorization header", async () => {
    await vi.resetModules();
    await import("./axiosConfig");

    localStorage.setItem("token", "legacy-fallback-token");
    const requestInterceptor = mocks.requestUse.mock.calls.at(-1)[0];
    const config = requestInterceptor({ url: "/auth/me", method: "get", headers: {} });

    expect(config.headers.Authorization).toBe("Bearer legacy-fallback-token");
  });
});
