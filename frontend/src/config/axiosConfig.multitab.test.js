import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), requestUse: vi.fn(), responseUse: vi.fn(),
  defaults: { headers: { common: {} } },
}));
vi.mock("axios", () => ({ default: {
  get: mocks.get, post: mocks.post, defaults: mocks.defaults,
  interceptors: { request: { use: mocks.requestUse }, response: { use: mocks.responseUse } },
} }));
vi.mock("@/lib/axios-cache", () => ({ installAxiosCache: vi.fn(), clearAxiosCache: vi.fn() }));
vi.mock("@/lib/httpResilience", () => ({ installAxiosResilience: vi.fn() }));
vi.mock("@/lib/sessionTelemetry", () => ({ recordSessionEvent: vi.fn() }));
vi.mock("@/lib/appNavigation", () => ({ navigateInternal: vi.fn() }));

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

describe("browser tabs sharing one rotating session", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    mocks.defaults.headers.common = {};
    localStorage.setItem("user", JSON.stringify({ id: "u1", tenant_id: "t1" }));
    localStorage.setItem("token_ts", String(Date.now() - 91 * 60 * 1000));
    localStorage.setItem("refresh_token", "refresh-1");
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("serializes two tab renewals and reads the current refresh token only after acquiring the origin lock", async () => {
    // Separate module instances model independent JS realms. They share only
    // browser-origin storage and the browser's lock queue, just like real tabs.
    let tail = Promise.resolve();
    const locks = { request: vi.fn((_name, work) => {
      const next = tail.then(work);
      tail = next.catch(() => {});
      return next;
    }) };
    vi.stubGlobal("navigator", { locks });
    const winner = deferred();
    mocks.post.mockImplementation(async (_url, body) => {
      if (body.refresh_token === "refresh-1") {
        await winner.promise;
        return { data: { access_token: "access-2", refresh_token: "refresh-2" } };
      }
      if (body.refresh_token === "refresh-2") {
        return { data: { access_token: "access-3", refresh_token: "refresh-3" } };
      }
      throw { response: { status: 401 } };
    });
    const tabA = await import("./axiosConfig");
    vi.resetModules();
    const tabB = await import("./axiosConfig");
    const first = tabA.keepActiveSessionAlive();
    const second = tabB.keepActiveSessionAlive();
    await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
    winner.resolve();
    await expect(Promise.all([first, second])).resolves.toEqual([
      { refreshed: true }, { refreshed: true },
    ]);
    expect(mocks.post.mock.calls.map(call => call[1].refresh_token)).toEqual(["refresh-1", "refresh-2"]);
    expect(localStorage.getItem("refresh_token")).toBe("refresh-3");
    expect(localStorage.getItem("user")).not.toBeNull();
  });

  it("does not let a stale in-memory bearer hide a valid rotated HttpOnly-cookie session", async () => {
    vi.stubGlobal("navigator", {});
    const tab = await import("./axiosConfig");
    mocks.defaults.headers.common.Authorization = "Bearer expired-access";
    mocks.post.mockRejectedValue({ response: { status: 401 } });
    mocks.get.mockImplementation(async (_url, config) => {
      if (config._cookieAuthOnly) return { data: { id: "u1", tenant_id: "t1" } };
      throw { response: { status: 401 } };
    });
    await expect(tab.keepActiveSessionAlive()).resolves.toEqual({ sessionRecovered: true });
    expect(localStorage.getItem("user")).not.toBeNull();
    expect(mocks.defaults.headers.common.Authorization).toBeUndefined();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    const request = mocks.requestUse.mock.calls.at(-1)[0];
    localStorage.setItem("token", "legacy-expired");
    const cookieRequest = request({ url: "/auth/me", method: "get", _cookieAuthOnly: true,
      headers: { Authorization: "Bearer expired-access", authorization: "Bearer expired-access" } });
    expect(cookieRequest.headers.Authorization).toBeUndefined();
    expect(cookieRequest.headers.authorization).toBeUndefined();
    const freshIdentity = request({ url: "/auth/me", method: "get", _noCache: true, headers: {} });
    expect(freshIdentity.headers["Cache-Control"]).toBe("no-cache, no-store");
    expect(freshIdentity.headers.Pragma).toBe("no-cache");
  });

  it("preserves server revocation: two definitive identity rejections still end the session", async () => {
    vi.stubGlobal("navigator", {});
    const tab = await import("./axiosConfig");
    mocks.post.mockRejectedValue({ response: { status: 401 } });
    mocks.get.mockRejectedValue({ response: { status: 401 } });
    await expect(tab.keepActiveSessionAlive()).resolves.toEqual({ invalid: true });
    expect(localStorage.getItem("user")).toBeNull();
  });

  it("does not rotate another account after waiting behind an existing tab", async () => {
    const acquired = deferred();
    vi.stubGlobal("navigator", { locks: { request: (_name, work) => acquired.promise.then(work) } });
    const tab = await import("./axiosConfig");
    const pending = tab.keepActiveSessionAlive();
    localStorage.setItem("user", JSON.stringify({ id: "u2", tenant_id: "t2" }));
    localStorage.setItem("refresh_token", "other-account-refresh");
    acquired.resolve();
    await expect(pending).resolves.toEqual({ transient: true });
    expect(mocks.post).not.toHaveBeenCalled();
    expect(localStorage.getItem("refresh_token")).toBe("other-account-refresh");
  });

  it("does not log out if cookie-only verification is unavailable during a deploy", async () => {
    vi.stubGlobal("navigator", {});
    const tab = await import("./axiosConfig");
    mocks.post.mockRejectedValue({ response: { status: 401 } });
    mocks.get.mockRejectedValueOnce({ response: { status: 401 } })
      .mockRejectedValueOnce({ response: { status: 503 } });
    await expect(tab.keepActiveSessionAlive()).resolves.toEqual({ transient: true });
    expect(localStorage.getItem("user")).not.toBeNull();
  });
});
