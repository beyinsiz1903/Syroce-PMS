import { describe, expect, it } from "vitest";

import { channelManagerRoutes } from "../channelManager";
import { hotelFeaturesAiRoutes } from "../hotelFeaturesAi";
import { marketplaceLoyaltyRoutes } from "../marketplaceLoyalty";
import { revenueRmsRoutes } from "../revenueRms";

const p = (component) => ({ type: "protected", component });
const pm = (component, moduleKey) => ({ type: "module", component, moduleKey });
const pa = p;

describe("module availability route gates", () => {
  it("guards HR entry points through the entitlement registry", () => {
    const routes = hotelFeaturesAiRoutes({ p, pm });
    for (const path of ["/hr", "/app/hr", "/staff-management", "/hr/shifts"]) {
      expect(routes.find((route) => route.path === path)).toMatchObject({
        type: "module",
        moduleKey: "hr",
      });
    }
  });

  it("preserves feature route type after composing protected props", () => {
    const revenueHub = channelManagerRoutes({ p, pa }).find((route) => route.path === "/app/revenue-hub");
    const rms = revenueRmsRoutes({ p }).find((route) => route.path === "/app/rms");
    const marketplace = marketplaceLoyaltyRoutes({ p }).find((route) => route.path === "/app/marketplace");

    expect(revenueHub).toMatchObject({ type: "feature", featureKey: "hidden_rms" });
    expect(rms).toMatchObject({ type: "feature", featureKey: "hidden_rms" });
    expect(marketplace).toMatchObject({ type: "feature", featureKey: "hidden_marketplace" });
  });
});
