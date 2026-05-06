import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Compass,
  Search,
  ExternalLink,
  EyeOff,
  Menu as MenuIcon,
  Lock,
  Globe,
} from "lucide-react";
import { NAV_ITEMS } from "@/config/navItems";
import { getRouteConfigs } from "@/routes/routeDefinitions";

/**
 * Module Discovery
 * Lists every protected route in the application alongside the sidebar
 * navigation state, so modules that do not appear in the sidebar are still
 * reachable. Purely client-side — no backend endpoint required.
 */
export default function ModuleDiscovery({ user, tenant, onLogout }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("hidden"); // hidden | all | visible

  // Build routes (skip redirects and parameterised / public ones).
  const allRoutes = useMemo(() => {
    try {
      const configs = getRouteConfigs({
        user: user || {},
        tenant: tenant || {},
        modules: [],
        isAuthenticated: true,
        onLogout: () => {},
        hasFeature: () => true,
      });
      return (configs || []).filter(
        (r) =>
          r?.path &&
          r.type !== "redirect" &&
          !r.path.includes(":") &&
          r.path !== "*" &&
          r.path !== "/",
      );
    } catch {
      return [];
    }
  }, [user, tenant]);

  const navPathSet = useMemo(() => {
    const s = new Set();
    for (const item of NAV_ITEMS || []) {
      if (item?.path) s.add(item.path);
    }
    return s;
  }, []);

  const navByPath = useMemo(() => {
    const m = new Map();
    for (const item of NAV_ITEMS || []) {
      if (item?.path) m.set(item.path, item);
    }
    return m;
  }, []);

  const rows = useMemo(() => {
    return allRoutes.map((r) => {
      const navItem = navByPath.get(r.path);
      const inNav = !!navItem;
      return {
        path: r.path,
        type: r.type,
        inNav,
        navLabel: navItem?.label || null,
        navGroup: navItem?.navGroup || null,
        tier: navItem?.tier || null,
        segment: (r.path.split("/").filter(Boolean)[0] || "root").toLowerCase(),
      };
    });
  }, [allRoutes, navByPath]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter === "hidden" && r.inNav) return false;
      if (filter === "visible" && !r.inNav) return false;
      if (!q) return true;
      return (
        r.path.toLowerCase().includes(q) ||
        (r.navLabel || "").toLowerCase().includes(q) ||
        r.segment.includes(q)
      );
    });
  }, [rows, query, filter]);

  const grouped = useMemo(() => {
    const groups = {};
    for (const r of filtered) {
      (groups[r.segment] ||= []).push(r);
    }
    return Object.entries(groups)
      .map(([k, v]) => [k, v.sort((a, b) => a.path.localeCompare(b.path))])
      .sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  const totals = useMemo(() => {
    const total = rows.length;
    const inNav = rows.filter((r) => r.inNav).length;
    return { total, inNav, hidden: total - inNav };
  }, [rows]);

  const prettyPath = (seg) => {
    if (seg === "root") return "Kök";
    return seg.charAt(0).toUpperCase() + seg.slice(1);
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="module-discovery" title="Modül Keşfi" subtitle="Sidebar'da görünmeyen sayfalar dahil tüm uygulama rotaları">
      <div className="p-4 space-y-4">
        {/* Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-3 rounded-lg bg-blue-50 text-blue-600">
                <Compass className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase">Toplam rota</div>
                <div className="text-2xl font-semibold">{totals.total}</div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-3 rounded-lg bg-green-50 text-green-600">
                <MenuIcon className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase">Menüde görünür</div>
                <div className="text-2xl font-semibold">{totals.inNav}</div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-3 rounded-lg bg-amber-50 text-amber-600">
                <EyeOff className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase">Gizli (menüsüz)</div>
                <div className="text-2xl font-semibold">{totals.hidden}</div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="p-3 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Yol veya etiket ara..."
                className="pl-9"
              />
            </div>
            <div className="flex gap-1 border rounded-md p-0.5 bg-gray-50">
              {[
                { v: "hidden", label: "Gizli" },
                { v: "all", label: "Tümü" },
                { v: "visible", label: "Menüde" },
              ].map((f) => (
                <button
                  key={f.v}
                  onClick={() => setFilter(f.v)}
                  className={`px-3 py-1 text-xs rounded ${
                    filter === f.v ? "bg-white shadow-sm font-medium" : "text-gray-600"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="text-xs text-gray-500">{filtered.length} sonuç</div>
          </CardContent>
        </Card>

        {/* Groups */}
        {grouped.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-gray-500 text-sm italic">
              Bu filtrede sayfa yok.
            </CardContent>
          </Card>
        ) : (
          grouped.map(([segment, items]) => (
            <Card key={segment}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Badge variant="outline" className="font-mono text-xs">
                    /{segment}
                  </Badge>
                  <span>{prettyPath(segment)}</span>
                  <span className="text-gray-400 font-normal">({items.length})</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y">
                  {items.map((r) => (
                    <div
                      key={r.path}
                      className="px-4 py-2 flex items-center gap-3 hover:bg-gray-50"
                    >
                      {r.type === "public" ? (
                        <Globe className="w-4 h-4 text-blue-500 flex-shrink-0" title="Public" />
                      ) : r.type === "module" ? (
                        <Lock className="w-4 h-4 text-indigo-500 flex-shrink-0" title="Modül korumalı" />
                      ) : (
                        <Lock className="w-4 h-4 text-gray-400 flex-shrink-0" title="Korumalı" />
                      )}
                      <code className="text-xs font-mono text-gray-700 flex-shrink-0">{r.path}</code>
                      {r.navLabel && (
                        <span className="text-sm text-gray-600 truncate">{r.navLabel}</span>
                      )}
                      <div className="flex-1" />
                      {r.navGroup && (
                        <Badge variant="outline" className="text-[10px]">
                          {r.navGroup}
                        </Badge>
                      )}
                      {r.tier && (
                        <Badge variant="outline" className="text-[10px]">
                          {r.tier}
                        </Badge>
                      )}
                      {r.inNav ? (
                        <Badge className="bg-green-100 text-green-700 border-green-300 text-[10px]">
                          menüde
                        </Badge>
                      ) : (
                        <Badge className="bg-amber-100 text-amber-700 border-amber-300 text-[10px]">
                          gizli
                        </Badge>
                      )}
                      <Link to={r.path}>
                        <Button size="sm" variant="ghost" className="h-7">
                          <ExternalLink className="w-3.5 h-3.5" />
                        </Button>
                      </Link>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </Layout>
  );
}
