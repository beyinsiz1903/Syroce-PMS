import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LoadingFallback, RouteContentLoadingFallback } from "../ProtectedRoute";

describe("route ProductState fallbacks", () => {
  it("uses the shared loading state for every route-level lazy boundary", () => {
    render(<LoadingFallback />);

    expect(screen.getByTestId("product-state")).toHaveAttribute("data-state", "loading");
    expect(screen.getByText("Veriler yükleniyor")).toBeInTheDocument();
  });

  it("keeps layout-owned route loading inside the shared compact state", () => {
    render(<RouteContentLoadingFallback />);

    expect(screen.getByTestId("route-content-loading")).toContainElement(screen.getByTestId("product-state"));
    expect(screen.getByTestId("product-state")).toHaveAttribute("data-state", "loading");
  });
});
