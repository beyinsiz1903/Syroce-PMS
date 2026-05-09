import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
    <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
      <PageHeader
        icon={Compass}
        title="Modül Keşfi"
        subtitle="Tanımlı tüm rotalar ve sidebar görünürlük durumu — yetim sayfaları (menüsüz) buradan keşfedin"
      />

      {/* Summary KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <KpiCard
          icon={Compass}
          label="Toplam rota"
          value={totals.total}
          intent="info"
          active={filter === "all"}
          onClick={() => setFilter("all")}
        />
        <KpiCard
          icon={MenuIcon}
          label="Menüde görünür"
          value={totals.inNav}
          intent="success"
          active={filter === "visible"}
          onClick={() => setFilter("visible")}
        />
        <KpiCard
          icon={EyeOff}
          label="Gizli (menüsüz)"
          value={totals.hidden}
          intent="warning"
          highlight={totals.hidden > 0}
          active={filter === "hidden"}
          onClick={() => setFilter("hidden")}
        />
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-3 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Yol veya etiket ara..."
              className="pl-9"
              aria-label="Rota arama"
            />
          </div>
          <Tabs value={filter} onValueChange={setFilter}>
            <TabsList>
              <TabsTrigger value="hidden">Gizli</TabsTrigger>
              <TabsTrigger value="all">Tümü</TabsTrigger>
              <TabsTrigger value="visible">Menüde</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="text-xs text-slate-500">{filtered.length} sonuç</div>
        </CardContent>
      </Card>

      {/* Groups */}
      {grouped.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-slate-500 text-sm italic">
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
                <span className="text-slate-400 font-normal">({items.length})</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y">
                {items.map((r) => (
                  <div
                    key={r.path}
                    className="px-4 py-2 flex items-center gap-3 hover:bg-slate-50"
                  >
                    {r.type === "public" ? (
                      <Globe className="w-4 h-4 text-indigo-500 flex-shrink-0" aria-label="Public route" />
                    ) : r.type === "module" ? (
                      <Lock className="w-4 h-4 text-indigo-600 flex-shrink-0" aria-label="Modül korumalı" />
                    ) : (
                      <Lock className="w-4 h-4 text-slate-400 flex-shrink-0" aria-label="Korumalı" />
                    )}
                    <code className="text-xs font-mono text-slate-700 flex-shrink-0">{r.path}</code>
                    {r.navLabel && (
                      <span className="text-sm text-slate-600 truncate">{r.navLabel}</span>
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
                      <StatusBadge intent="success">menüde</StatusBadge>
                    ) : (
                      <StatusBadge intent="warning">gizli</StatusBadge>
                    )}
                    <Button asChild size="sm" variant="ghost" className="h-7" aria-label={`${r.path} sayfasına git`}>
                      <Link to={r.path}>
                        <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                      </Link>
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
