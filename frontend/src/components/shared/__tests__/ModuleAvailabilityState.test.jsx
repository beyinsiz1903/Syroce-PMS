import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  ModuleAvailabilityState,
  ModuleLoadError,
  moduleLoadState,
} from "@/components/shared/ModuleAvailabilityState";

describe("ModuleAvailabilityState", () => {
  it("classifies setup, throttling and temporary failures", () => {
    expect(moduleLoadState({ response: { status: 403 } })).toBe("setup");
    expect(moduleLoadState({ response: { status: 429 } })).toBe("throttled");
    expect(moduleLoadState({ response: { status: 404 } })).toBe("temporary");
    expect(moduleLoadState({ response: { status: 503 } })).toBe("temporary");
  });

  it("shows explicit setup guidance instead of redirecting", () => {
    render(<ModuleAvailabilityState moduleName="Spa & Wellness" reason="disabled" />);
    expect(screen.getByText("Kurulum gerekli")).toBeDefined();
    expect(screen.getByText('Bu modül tesisinizde etkin değil. Paketinizi veya kullanıcı yetkinizi kontrol edin.')).toBeDefined();
  });

  it("offers retry for exhausted 429 responses", () => {
    const retry = vi.fn();
    render(<ModuleLoadError moduleName="MICE takvimi" error={{ response: { status: 429 } }} onRetry={retry} />);
    expect(screen.getByText("İstek sınırına ulaşıldı")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Yeniden Dene" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
