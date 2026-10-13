import { describe, expect, it } from "vitest";

import {
  NIGHT_AUDIT_RUN_TIMEOUT_MS,
  confirmsNightAuditAdvance,
  isNightAuditTimeout,
  nextIsoDate,
  hasCurrentCatchupSimulation,
  requiresCatchupSimulationMode,
} from "@/lib/nightAuditRunSafety";

describe("night audit run safety", () => {
  it.each([2, 38, 365])("guides a %i-day backlog through simulation without allowing a permission bypass", (days) => {
    expect(requiresCatchupSimulationMode(days, false, true)).toBe(true);
    expect(requiresCatchupSimulationMode(days, true, false)).toBe(true);
    expect(requiresCatchupSimulationMode(days, true, true)).toBe(false);
  });
  it("preserves normal one-day closing", () => {
    expect(requiresCatchupSimulationMode(1, false, false)).toBe(false);
  });
  it("requires a completed simulation reference for exactly the open day", () => {
    expect(hasCurrentCatchupSimulation(null, "2026-09-05")).toBe(false);
    expect(hasCurrentCatchupSimulation({ date: "2026-09-05" }, "2026-09-05")).toBe(false);
    expect(hasCurrentCatchupSimulation({ date: "2026-09-05", runId: "sim-1" }, "2026-09-05")).toBe(true);
    expect(hasCurrentCatchupSimulation({ date: "2026-09-05", runId: "sim-1" }, "2026-09-06")).toBe(false);
  });
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
