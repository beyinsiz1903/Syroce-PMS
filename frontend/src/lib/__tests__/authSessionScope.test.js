import { beforeEach, describe, expect, it } from "vitest";
import {
  blockTabAfterExternalSessionChange,
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
});
