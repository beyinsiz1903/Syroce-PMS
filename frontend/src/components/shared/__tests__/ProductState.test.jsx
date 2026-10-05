import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import ProductState from "@/components/shared/ProductState";

describe("ProductState", () => {
  it("announces a consistent loading state without a recovery action", () => {
    render(<ProductState state="loading" moduleName="Rezervasyon takvimi" showDashboardLink={false} />);

    expect(screen.getByTestId("product-state").dataset.state).toBe("loading");
    expect(screen.getByRole("status").textContent).toContain("Veriler yükleniyor");
    expect(screen.queryByRole("button", { name: "Yeniden dene" })).toBeNull();
  });

  it("keeps retry behavior inside the shared error state", () => {
    const retry = vi.fn();
    render(<ProductState state="error" moduleName="Raporlar" onRetry={retry} showDashboardLink={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("renders an explicit empty state for unconfigured workspaces", () => {
    render(<ProductState state="empty" moduleName="Kanal Operasyon Merkezi" compact showDashboardLink={false} />);

    expect(screen.getByTestId("product-state").dataset.state).toBe("empty");
    expect(screen.getByText("Henüz gösterilecek kayıt yok")).toBeDefined();
  });
});
