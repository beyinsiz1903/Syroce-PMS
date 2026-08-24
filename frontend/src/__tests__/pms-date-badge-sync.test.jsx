import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PMSDateBadge from "@/components/PMSDateBadge";
import { BUSINESS_DATE_CHANGED_EVENT } from "@/lib/businessDateEvents";

vi.mock("@/api/axios", () => ({
  default: { get: vi.fn() },
}));
vi.mock("@/lib/prefetch", () => ({ prefetchNightAudit: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

describe("PMSDateBadge business-date synchronization", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("user", JSON.stringify({ tenant_id: "tenant-1" }));
    sessionStorage.setItem("pms_bd_cache_v1", JSON.stringify({
      bd: "2026-07-16",
      tid: "tenant-1",
      t: Date.now(),
    }));
  });

  it("updates immediately when a night audit publishes the new business date", async () => {
    render(<MemoryRouter><PMSDateBadge /></MemoryRouter>);
    expect(screen.getByText("16 Tem 2026")).toBeInTheDocument();

    fireEvent(window, new CustomEvent(BUSINESS_DATE_CHANGED_EVENT, {
      detail: {
        businessDate: "2026-08-14",
        metadata: {
          business_date: "2026-08-14",
          update_source: "night_audit",
          audit_run_id: "run-14",
        },
      },
    }));

    await waitFor(() => expect(screen.getByText("14 Ağu 2026")).toBeInTheDocument());
    expect(JSON.parse(sessionStorage.getItem("pms_bd_cache_v1")).bd).toBe("2026-08-14");
    expect(screen.getByTestId("pms-date-badge").parentElement).toHaveAttribute(
      "title",
      "Son Night Audit: run-14",
    );
  });
});

describe("PMSDateBadge dense content safety", () => {
  it.each([
    "/app/reservation-calendar",
    "/app/academy",
    "/app/academy-report",
    "/app/academy-manage",
  ])("does not cover content on %s", (pathname) => {
    render(
      <MemoryRouter initialEntries={[pathname]}>
        <PMSDateBadge />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("pms-date-badge")).not.toBeInTheDocument();
  });
});

describe("PMSDateBadge origin transparency", () => {
  it("explains that an initialized date is not a completed night audit", () => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("user", JSON.stringify({ tenant_id: "tenant-1" }));
    sessionStorage.setItem("pms_bd_cache_v1", JSON.stringify({
      bd: "2026-08-22",
      meta: {
        business_date: "2026-08-22",
        update_source: "initialization",
        initialization_reason: "earliest_unresolved_arrival",
      },
      tid: "tenant-1",
      t: Date.now(),
    }));

    render(<MemoryRouter><PMSDateBadge /></MemoryRouter>);

    expect(screen.getByTestId("pms-date-badge").parentElement).toHaveAttribute(
      "title",
      "İş günü başlangıç kaydından oluşturuldu; Night Audit değildir.",
    );
  });
});
