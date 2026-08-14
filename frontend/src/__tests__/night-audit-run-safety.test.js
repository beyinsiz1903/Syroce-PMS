import { describe, expect, it } from "vitest";

import {
  NIGHT_AUDIT_RUN_TIMEOUT_MS,
  confirmsNightAuditAdvance,
  isNightAuditTimeout,
  nextIsoDate,
} from "@/lib/nightAuditRunSafety";

describe("night audit run safety", () => {
  it("allows long-running audits more than the global 30 second timeout", () => {
    expect(NIGHT_AUDIT_RUN_TIMEOUT_MS).toBeGreaterThan(30_000);
  });

  it("classifies only transport timeouts as timeout outcomes", () => {
    expect(isNightAuditTimeout({ code: "ECONNABORTED" })).toBe(true);
    expect(isNightAuditTimeout({ code: "ETIMEDOUT" })).toBe(true);
    expect(isNightAuditTimeout({ response: { status: 500 } })).toBe(false);
  });

  it("confirms a timeout only when the business date advanced exactly one day", () => {
    expect(nextIsoDate("2026-08-13")).toBe("2026-08-14");
    expect(confirmsNightAuditAdvance("2026-08-13", "2026-08-14")).toBe(true);
    expect(confirmsNightAuditAdvance("2026-08-13", "2026-08-13")).toBe(false);
    expect(confirmsNightAuditAdvance("2026-08-13", "2026-08-15")).toBe(false);
  });
});
