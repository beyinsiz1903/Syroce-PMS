import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";

import ObservabilityDashboard from "@/pages/ObservabilityDashboard";

vi.mock("axios", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const responses = {
  "/observability/metrics": {
    event_throughput: 0,
    messaging_delivery: { success_count: 0, failure_count: 0, delivery_rate: 0 },
    websocket_latency: { avg: 12 },
    ml_execution_time: { avg: 0.2 },
    autopricing: { success_rate: 1 },
    reservation_sync_lag: { avg: 30 },
  },
  "/observability/traces/summary?hours=1": {
    total_requests: 851,
    total_slow: 0,
    active_traces: 3,
    total_errors: 2,
    error_rate: 0.0024,
    endpoints: [{ path: "/api/pms/rooms", count: 3, avg_ms: 85.7, p95_ms: 95.86, max_ms: 95.86, errors: 0, slow: 0 }],
  },
  "/observability/errors/summary?hours=24": { total_errors: 0, by_severity: {}, top_errors: [] },
  "/observability/health": { overall_status: "healthy", services: { mongodb: { status: "healthy", latency_ms: 20.17 } } },
  "/observability/traces?limit=20&slow_only=false": [],
};

beforeEach(() => {
  axios.get.mockImplementation((url) => Promise.resolve({ data: responses[url] }));
  axios.post.mockResolvedValue({ data: {} });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ObservabilityDashboard", () => {
  it("renders readable Turkish labels and distinguishes missing delivery data from zero percent", async () => {
    render(<ObservabilityDashboard />);

    expect(await screen.findByRole("heading", { name: "Sistem Sağlığı" })).toBeInTheDocument();
    expect(screen.getByText("Veritabanı")).toBeInTheDocument();
    expect(screen.getByTestId("requests-metric")).toHaveTextContent("851");
    expect(screen.getByTestId("delivery-rate-metric")).toHaveTextContent("Veri yok");
    expect(screen.getByText("Oda bilgileri")).toBeInTheDocument();
    expect(screen.queryByText("Event Throughput")).not.toBeInTheDocument();
    expect(screen.queryByText("Messaging DR")).not.toBeInTheDocument();
  });

  it("requires confirmation before saving buffered technical data", async () => {
    render(<ObservabilityDashboard />);
    await screen.findByRole("heading", { name: "Sistem Sağlığı" });

    fireEvent.click(screen.getByText("Gelişmiş teknik işlemler"));
    fireEvent.click(screen.getByTestId("flush-traces-btn"));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Teknik veriler kaydedilsin mi?");
    expect(axios.post).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/observability/traces/flush", {}));
  });
});
