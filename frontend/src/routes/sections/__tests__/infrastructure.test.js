import { describe, expect, it, vi } from "vitest";

import { infrastructureRoutes } from "@/routes/sections/infrastructure";

describe("infrastructure routes", () => {
  it("protects observability as a super-admin-only technical screen", () => {
    const p = vi.fn((component) => ({ type: "protected", component }));
    const pa = vi.fn((component) => ({ type: "protected", component, requireSuperAdmin: true }));

    const routes = infrastructureRoutes({ p, pa });
    const observability = routes.find((route) => route.path === "/observability");

    expect(observability.requireSuperAdmin).toBe(true);
    expect(observability.wrapLayout).toBe(true);
    expect(observability.layoutModule).toBe("observability");
  });

  it("protects every platform screen exposed in super-admin navigation", () => {
    const p = vi.fn((component) => ({ type: "protected", component }));
    const pa = vi.fn((component) => ({ type: "protected", component, requireSuperAdmin: true }));
    const routes = infrastructureRoutes({ p, pa });

    for (const path of [
      "/observability",
      "/integration-observability",
      "/infra-hardening",
      "/production-golive",
    ]) {
      expect(routes.find((route) => route.path === path)?.requireSuperAdmin, path).toBe(true);
    }
  });

  it("keeps the legacy credential-vault URL as a canonical, hash-preserving alias", () => {
    const p = vi.fn((component) => ({ type: "protected", component }));
    const pa = vi.fn((component) => ({ type: "protected", component, requireSuperAdmin: true }));
    const route = infrastructureRoutes({ p, pa }).find((candidate) => candidate.path === "/integration-credentials");

    expect(route).toMatchObject({
      type: "redirect",
      to: "/admin/integration-credentials",
      preserveLocation: true,
    });
  });
});
