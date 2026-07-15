import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { EntitlementProvider, useEntitlements } from "../EntitlementContext";
import { vi } from "vitest";
import axios from "axios";

vi.mock("axios");

const TestMiceComponent = () => {
    const { entitlements, getLimit, hasFeature, hasModule } = useEntitlements();
    
    if (!entitlements) return <div data-testid="loading">Yükleniyor...</div>;

    const canSeeMice = hasModule('mice');
    const hasBanquet = entitlements?.mice?.features?.includes('banquet_operations');
    
    const eventsLimit = entitlements?.mice?.limits?.concurrent_events ?? 0;
    const eventsUsage = entitlements?.mice?.usage?.concurrent_events ?? 0;
    const eventsLimitHit = eventsLimit > 0 && eventsUsage >= eventsLimit;

    return (
        <div>
            {canSeeMice ? <div data-testid="mice-menu">MICE Menüsü</div> : <div data-testid="no-mice">Gizli</div>}
            {hasBanquet ? <button data-testid="beo-btn">BEO Yazdır</button> : <span data-testid="no-beo">BEO Yok</span>}
            <button data-testid="new-event-btn" disabled={eventsLimitHit}>Yeni Etkinlik</button>
        </div>
    );
};

describe("BehaviorContext - MICE Entitlements", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        const localStorageMock = {
            getItem: vi.fn(),
            setItem: vi.fn(),
            removeItem: vi.fn(),
            clear: vi.fn()
        };
        Object.defineProperty(window, 'localStorage', { value: localStorageMock });
    });

    test("Pro tier shows MICE, BEO button, and disables New Event button if limit hit", async () => {
        axios.get.mockResolvedValue({
            data: {
                tenant_id: "t1",
                modules: ["mice", "pos_fnb"],
                entitlements: {
                    mice: {
                        tier: "pro",
                        features: ["banquet_operations", "proposals_contracts"],
                        limits: { concurrent_events: 50 },
                        usage: { concurrent_events: 50 }
                    }
                }
            }
        });

        render(
            <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                <TestMiceComponent />
            </EntitlementProvider>
        );

        await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());

        expect(screen.getByTestId("mice-menu")).toBeInTheDocument();
        expect(screen.getByTestId("beo-btn")).toBeInTheDocument();
        expect(screen.getByTestId("new-event-btn")).toBeDisabled();
    });

    test("Basic tier hides BEO button", async () => {
        axios.get.mockResolvedValue({
            data: {
                tenant_id: "t1",
                modules: ["mice"],
                entitlements: {
                    mice: {
                        tier: "basic",
                        features: [], 
                        limits: { concurrent_events: 5 },
                        usage: { concurrent_events: 2 }
                    }
                }
            }
        });

        render(
            <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                <TestMiceComponent />
            </EntitlementProvider>
        );

        await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());

        expect(screen.getByTestId("mice-menu")).toBeInTheDocument();
        expect(screen.getByTestId("no-beo")).toBeInTheDocument();
        expect(screen.queryByTestId("beo-btn")).not.toBeInTheDocument();
        expect(screen.getByTestId("new-event-btn")).not.toBeDisabled();
    });

    test("Hides MICE menu if module not enabled", async () => {
        axios.get.mockResolvedValue({
            data: {
                tenant_id: "t1",
                modules: ["hotel_rooms"], 
                entitlements: {}
            }
        });

        render(
            <EntitlementProvider currentTenantId="t1" isSuperAdmin={false}>
                <TestMiceComponent />
            </EntitlementProvider>
        );

        await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());

        expect(screen.getByTestId("no-mice")).toBeInTheDocument();
        expect(screen.queryByTestId("mice-menu")).not.toBeInTheDocument();
    });
});
