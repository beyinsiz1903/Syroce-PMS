import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PMSDateBadge from "@/components/PMSDateBadge";
import { BUSINESS_DATE_CHANGED_EVENT } from "@/lib/businessDateEvents";

vi.mock("@/api/axios", () => ({
  default: { get: vi.fn() },
}));
vi.mock("@/lib/prefetch", () => ({ prefetchNightAudit: vi.fn() }));
let activeLanguage = "tr";
const translations = {
  tr: {
    "nightAudit.lastAudit": "Son Night Audit: {{id}}",
    "nightAudit.reviewPreparation": "Gün sonu hazırlığını incele",
    "nightAudit.reviewEndOfDay": "Gün Sonunu İncele",
    "nightAudit.initializedDateNotice": "İş günü başlangıç kaydından oluşturuldu; Night Audit değildir.",
  },
  en: {
    "nightAudit.lastAudit": "Last Night Audit: {{id}}",
    "nightAudit.reviewPreparation": "Review end-of-day preparation",
    "nightAudit.reviewEndOfDay": "Review End of Day",
    "nightAudit.initializedDateNotice": "The business date was created from the opening record; this is not a completed Night Audit.",
  },
};
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    i18n: { language: activeLanguage, resolvedLanguage: activeLanguage },
    t: (key, options) => (translations[activeLanguage]?.[key] || options?.defaultValue || options || key)
      .replace?.("{{id}}", options?.id) ?? key,
  }),
}));

describe("PMSDateBadge business-date synchronization", () => {
  beforeEach(() => {
    activeLanguage = "tr";
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

  it("opens the controlled review screen instead of presenting navigation as an execution", () => {
    render(<MemoryRouter><PMSDateBadge /></MemoryRouter>);

    const reviewButton = screen.getByTestId("pms-date-stale-warning");
    expect(reviewButton).toHaveTextContent("Gün Sonunu İncele");
    expect(reviewButton).toHaveAttribute("title", "Gün sonu hazırlığını incele");
  });

  it("renders the business date and review action in English when English is selected", () => {
    activeLanguage = "en";
    render(<MemoryRouter><PMSDateBadge /></MemoryRouter>);

    expect(screen.getByText("Jul 16, 2026")).toBeInTheDocument();
    expect(screen.getByTestId("pms-date-stale-warning")).toHaveTextContent("Review End of Day");
    expect(screen.getByTestId("pms-date-stale-warning")).toHaveAttribute(
      "title",
      "Review end-of-day preparation",
    );
  });
});

describe("PMSDateBadge dense content safety", () => {
  it.each([
    "/app/reservation-calendar",
    "/app/academy",
    "/app/academy-report",
    "/app/academy-manage",
  ])("stays in normal layout flow on %s", (pathname) => {
    render(
      <MemoryRouter initialEntries={[pathname]}>
        <PMSDateBadge />
      </MemoryRouter>,
    );

    const badge = screen.getByTestId("pms-date-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.parentElement).not.toHaveClass("fixed");
  });

  it("provides a dedicated layout row when embedded by Layout", () => {
    render(
      <MemoryRouter initialEntries={["/app/reservation-calendar"]}>
        <PMSDateBadge inLayout />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("layout-business-date-bar")).toContainElement(
      screen.getByTestId("pms-date-badge"),
    );
  });
});

describe("PMSDateBadge origin transparency", () => {
  it("explains that an initialized date is not a completed night audit", () => {
    activeLanguage = "tr";
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
