import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  ModuleAvailabilityState,
  ModuleLoadError,
  moduleLoadState,
} from "@/components/shared/ModuleAvailabilityState";

describe("ModuleAvailabilityState", () => {
  it("classifies setup, throttling and temporary failures", () => {
    expect(moduleLoadState({ response: { status: 403 } })).toBe("forbidden");
    expect(moduleLoadState({ response: { status: 429 } })).toBe("throttled");
    expect(moduleLoadState({ response: { status: 404 } })).toBe("error");
    expect(moduleLoadState({ response: { status: 503 } })).toBe("error");
  });

  it("shows explicit setup guidance instead of redirecting", () => {
    render(<ModuleAvailabilityState moduleName="Spa & Wellness" reason="disabled" />);
    expect(screen.getByText("Kurulum gerekli")).toBeDefined();
    expect(screen.getByText('Spa & Wellness: Bu modül tesisinizde etkin değil veya bağlantısı henüz tamamlanmadı. Paket, modül ve entegrasyon ayarlarını kontrol edin.')).toBeDefined();
  });

  it("offers retry for exhausted 429 responses", () => {
    const retry = vi.fn();
    render(<ModuleLoadError moduleName="MICE takvimi" error={{ response: { status: 429 } }} onRetry={retry} />);
    expect(screen.getByText("İstek sınırına ulaşıldı")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
