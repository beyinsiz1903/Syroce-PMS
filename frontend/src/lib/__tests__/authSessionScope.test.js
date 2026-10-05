import { beforeEach, describe, expect, it } from "vitest";
import {
  blockTabAfterExternalSessionChange,
  clearAuthScopedSessionStorage,
  clearTabAuthScope,
  isForeignIdentityForTab,
  isTabAuthBlocked,
  readSharedAuthUser,
  readTabAuthSubject,
  rememberTabAuthSubject,
} from "../authSessionScope";

const hotelAUser = { id: "user-a", tenant_id: "hotel-a" };
const hotelBUser = { id: "user-b", tenant_id: "hotel-b" };

describe("authSessionScope", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("remembers an authenticated subject only for the current tab", () => {
    expect(rememberTabAuthSubject(hotelAUser)).toBe("user-a:hotel-a");
    expect(readTabAuthSubject()).toBe("user-a:hotel-a");
    expect(isForeignIdentityForTab(hotelAUser)).toBe(false);
  });

  it("detects a different user or hotel before it can repaint the tab", () => {
    rememberTabAuthSubject(hotelAUser);
    expect(isForeignIdentityForTab(hotelBUser)).toBe(true);
    expect(isForeignIdentityForTab({ ...hotelAUser, tenant_id: "hotel-b" })).toBe(true);
  });

  it("blocks only the stale tab after an external session switch", () => {
    rememberTabAuthSubject(hotelAUser);
    blockTabAfterExternalSessionChange();
    expect(readTabAuthSubject()).toBeNull();
    expect(isTabAuthBlocked()).toBe(true);

    rememberTabAuthSubject(hotelBUser);
    expect(isTabAuthBlocked()).toBe(false);
    expect(readTabAuthSubject()).toBe("user-b:hotel-b");
  });

  it("blocks a duplicated tab when shared browser login changes hotel", () => {
    // A duplicated tab inherits its own sessionStorage snapshot from Hotel A;
    // browser-level localStorage can then be changed by a Hotel B login.
    rememberTabAuthSubject(hotelAUser);
    localStorage.setItem("user", JSON.stringify(hotelBUser));

    expect(isForeignIdentityForTab(readSharedAuthUser())).toBe(true);
    blockTabAfterExternalSessionChange();

    expect(isTabAuthBlocked()).toBe(true);
    expect(readTabAuthSubject()).toBeNull();
  });

  it("parses the shared snapshot defensively", () => {
    localStorage.setItem("user", JSON.stringify(hotelAUser));
    expect(readSharedAuthUser()).toEqual(hotelAUser);
    localStorage.setItem("user", "not-json");
    expect(readSharedAuthUser()).toBeNull();
  });

  it("clears tab markers on an explicit local logout", () => {
    rememberTabAuthSubject(hotelAUser);
    clearTabAuthScope();
    expect(readTabAuthSubject()).toBeNull();
    expect(isTabAuthBlocked()).toBe(false);
  });

  it("clears every auth-scoped cache without removing neutral preferences", () => {
    rememberTabAuthSubject(hotelAUser);
    sessionStorage.setItem("notif_cache_v1", "notifications");
    sessionStorage.setItem("pms_bd_cache_v1", "business-date");
    sessionStorage.setItem("push_status_cache_v1", "push");
    sessionStorage.setItem("pms_edit_booking", "booking");
    sessionStorage.setItem("simulation_active", "true");
    sessionStorage.setItem("settings:activeTab", "users");

    clearAuthScopedSessionStorage();

    expect(readTabAuthSubject()).toBeNull();
    expect(isTabAuthBlocked()).toBe(false);
    expect(sessionStorage.getItem("notif_cache_v1")).toBeNull();
    expect(sessionStorage.getItem("pms_bd_cache_v1")).toBeNull();
    expect(sessionStorage.getItem("push_status_cache_v1")).toBeNull();
    expect(sessionStorage.getItem("pms_edit_booking")).toBeNull();
    expect(sessionStorage.getItem("simulation_active")).toBeNull();
    expect(sessionStorage.getItem("settings:activeTab")).toBe("users");
  });
});
