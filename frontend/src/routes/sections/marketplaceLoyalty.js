import {
  MarketplaceModule, SuppliesMarket, VendorPortal, LoyaltyModule,
  HotelInventory, InventoryTransferHistory, TemplateManager,
  HotelNetwork,
} from "./lazyPages";

export function marketplaceLoyaltyRoutes({ p }) {
  return [
    // ── Marketplace ────────────────────────────────────
    { path: "/marketplace", ...p(MarketplaceModule), type: "feature", featureKey: "hidden_marketplace", moduleName: "Pazar Yeri", wrapLayout: true, layoutModule: "marketplace" },
    { path: "/app/marketplace", ...p(MarketplaceModule), type: "feature", featureKey: "hidden_marketplace", moduleName: "Pazar Yeri", wrapLayout: true, layoutModule: "marketplace" },
    { path: "/app/hotel-network", ...p(HotelNetwork), wrapLayout: true, layoutModule: "pms" },
    { path: "/app/supplies-market", ...p(SuppliesMarket), wrapLayout: true, layoutModule: "supplies_market" },
    { path: "/vendor", type: "public", component: VendorPortal },
    { path: "/vendor/*", type: "public", component: VendorPortal },

    // ── Loyalty & Inventory ────────────────────────────
    { path: "/loyalty", ...p(LoyaltyModule), wrapLayout: true, layoutModule: "loyalty" },
    { path: "/hotel-inventory", ...p(HotelInventory), wrapLayout: true },
    { path: "/hotel-inventory/transfers", ...p(InventoryTransferHistory), wrapLayout: true },
    { path: "/templates", ...p(TemplateManager), wrapLayout: true, layoutModule: "pms" },
  ];
}
