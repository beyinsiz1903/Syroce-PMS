import { describe, expect, it } from "vitest";

import { RouteRum } from "@/lib/routeRum";

describe("RouteRum", () => {
  it("keeps a measured SPA transition with the destination route", () => {
    let now = 100;
    const rum = new RouteRum({ enabled: true, now: () => now });

    rum.markTransition("/app/reservation-calendar");
    now = 280;
    rum.start("/app/reservation-calendar");

    expect(rum.current.navigation_ms).toBe(180);
    expect(rum.current.pathname).toBe("/app/reservation-calendar");
  });

  it("does not assign transition timing to a different route", () => {
    const rum = new RouteRum({ enabled: true, now: () => 100 });

    rum.markTransition("/app/dashboard");
    rum.start("/app/pms");

    expect(rum.current.navigation_ms).toBeNull();
  });
});
