import { describe, expect, it } from "vitest";

import { buildBusinessDateOriginCopy } from "@/lib/businessDateOriginCopy";

describe("business-date origin copy", () => {
  it("shows a completed manual Night Audit without leaking internal identifiers", () => {
    const actorId = "31b4de07-425f-4321-a6ce-dd492f6dc243";
    const auditRunId = "ae790df6-d3f3-491e-b456-bc44fcfec6ee";
    const copy = buildBusinessDateOriginCopy({
      business_date: "2026-08-23",
      update_source: "night_audit",
      initialization_reason: "earliest_unresolved_arrival",
      updated_at: "2026-08-26T13:50:10Z",
      trigger_source: "manual",
      updated_by: actorId,
      audit_run_id: auditRunId,
    }, {
      id: actorId,
      name: "Engin Tekdaş",
    });

    expect(copy.title).toBe("Night Audit tamamlandı");
    expect(copy.detail).toContain("Yeni PMS iş günü: 23 Ağustos 2026.");
    expect(copy.detail).toContain("Tamamlanma: 26 Ağustos 2026 16:50.");
    expect(copy.detail).toContain("Engin Tekdaş tarafından manuel olarak tamamlandı.");
    expect(copy.detail).not.toContain("çözülmemiş en eski aktif rezervasyon");
    expect(copy.detail).not.toContain(actorId);
    expect(copy.detail).not.toContain(auditRunId);
  });

  it("does not attribute a historical audit to the current user", () => {
    const copy = buildBusinessDateOriginCopy({
      business_date: "2026-08-24",
      update_source: "night_audit",
      trigger_source: "manual",
      updated_by: "another-user-id",
    }, {
      id: "current-user-id",
      name: "Engin Tekdaş",
    });

    expect(copy.detail).toContain("Yetkili kullanıcı tarafından manuel olarak tamamlandı.");
    expect(copy.detail).not.toContain("another-user-id");
    expect(copy.detail).not.toContain("Engin Tekdaş");
  });

  it("keeps initialization provenance understandable without technical records", () => {
    const copy = buildBusinessDateOriginCopy({
      business_date: "2026-08-22",
      update_source: "initialization",
      initialization_reason: "earliest_unresolved_arrival",
      updated_by: "system_business_date_bootstrap",
    });

    expect(copy.title).toBe("PMS iş günü güvenli başlangıç kaydından oluşturuldu");
    expect(copy.detail).toContain("Açık rezervasyonlar esas alınarak güvenli başlangıç tarihi oluşturuldu.");
    expect(copy.detail).not.toContain("system_business_date_bootstrap");
  });
});
