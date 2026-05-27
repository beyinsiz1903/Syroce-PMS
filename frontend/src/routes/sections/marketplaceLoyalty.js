import {
  MarketplaceModule, SuppliesMarket, VendorPortal, LoyaltyModule,
  HotelInventory, InventoryTransferHistory, TemplateManager,
} from "./lazyPages";

export function marketplaceLoyaltyRoutes({ p }) {
  return [
    // ── Marketplace ────────────────────────────────────
    { path: "/marketplace", ...p(MarketplaceModule), wrapLayout: true, layoutModule: "marketplace" },
    { path: "/app/marketplace", ...p(MarketplaceModule), wrapLayout: true, layoutModule: "marketplace" },
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
