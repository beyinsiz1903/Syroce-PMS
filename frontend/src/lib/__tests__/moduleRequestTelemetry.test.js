import { beforeEach, describe, expect, it } from "vitest";
import {
  moduleFailureContext,
  moduleForRequest,
  pseudonymousTenantScope,
  requestPath,
  tenantIdFromStorage,
} from "@/lib/moduleRequestTelemetry";

describe("module request telemetry context", () => {
  beforeEach(() => localStorage.clear());

  it("maps target API paths without retaining query values", () => {
    expect(moduleForRequest("/spa/services")).toBe("spa");
    expect(moduleForRequest("/mice/diary?date_from=2026-08-01")).toBe("mice");
    expect(moduleForRequest("/supplies-market/orders/mine")).toBe("marketplace");
    expect(moduleForRequest("/rms/dashboard-kpis")).toBe("rms");
    expect(requestPath("/hr/staff?email=private@example.com")).toBe("/hr/staff");
  });

  it("uses only the stable tenant identifier", () => {
    localStorage.setItem("tenant", JSON.stringify({ id: "tenant-42", name: "Private Hotel" }));
    expect(tenantIdFromStorage()).toBe("tenant-42");
    expect(pseudonymousTenantScope("tenant-42")).toMatch(/^t_[0-9a-f]{8}$/);
    expect(pseudonymousTenantScope("tenant-42")).toBe(pseudonymousTenantScope("tenant-42"));
  });

  it("builds sanitized tags for a final failure", () => {
    localStorage.setItem("tenant", JSON.stringify({ id: "tenant-42" }));
    const context = moduleFailureContext({
      config: { method: "get", url: "/hr/staff?email=private@example.com", _syroceRetryCount: 2 },
      response: { status: 503 },
    });
    expect(context).toEqual({
      module: "hr",
      tenantScope: pseudonymousTenantScope("tenant-42"),
      method: "GET",
      path: "/hr/staff",
      status: 503,
      retryCount: 2,
    });
  });
});
