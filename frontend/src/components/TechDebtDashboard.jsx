import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  Bug, AlertTriangle, CheckCircle, Target, Clock, Flame,
  ChevronDown, ChevronUp, RefreshCw, TrendingDown,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";

const PRIORITY_COLORS = {
  1: "border-red-500/30 bg-red-500/5",
  2: "border-orange-500/30 bg-orange-500/5",
  3: "border-yellow-500/30 bg-yellow-500/5",
  4: "border-blue-500/30 bg-blue-500/5",
  5: "border-zinc-700 bg-zinc-900",
};

const GRADE_STYLES = {
  A: "text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
  B: "text-blue-400 bg-blue-500/15 border-blue-500/30",
  C: "text-yellow-400 bg-yellow-500/15 border-yellow-500/30",
  D: "text-red-400 bg-red-500/15 border-red-500/30",
};

function CategoryCard({ cat }) {
  const [open, setOpen] = useState(false);
  const pct = cat.count > 0 ? Math.round((cat.weekly_target / cat.count) * 100) : 100;

  return (
    <div
      className={`border rounded-xl transition-all ${PRIORITY_COLORS[cat.priority] || "border-zinc-800"}`}
      data-testid={`debt-category-${cat.key}`}
    >
      <button
        className="w-full px-5 py-4 flex items-center justify-between text-left"
        onClick={() => setOpen(!open)}
        data-testid={`debt-toggle-${cat.key}`}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-zinc-800 text-xs font-bold text-zinc-300 shrink-0">
            P{cat.priority}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-zinc-200">{cat.label}</div>
            <div className="text-[10px] text-zinc-500 truncate">{cat.description}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <div className="text-right">
            <div className="text-lg font-bold font-mono text-zinc-100">{cat.count}</div>
            <div className="text-[10px] text-zinc-600 font-mono">{cat.effort_hours}s efor</div>
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
        </div>
      </button>

      {/* Progress bar */}
      <div className="px-5 pb-3">
        <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-1">
          <span>Haftalik hedef: {cat.weekly_target} test/hafta</span>
          <span>{cat.weeks_to_clear} hafta kaldi</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-700"
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </div>

      {/* Test list */}
      {open && cat.tests.length > 0 && (
        <div className="px-5 pb-4 space-y-1.5 border-t border-zinc-800/50 pt-3">
          {cat.tests.map((t, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] font-mono group">
              <Bug className="h-3 w-3 text-zinc-600 mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-zinc-300 truncate">{t.test_id}</div>
                <div className="text-zinc-600 truncate">{t.reason}</div>
                <div className="text-zinc-700">beri: {t.since}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TechDebtDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async (showToast = false) => {
    try {
      const res = await axios.get("/ops/dashboard/tech-debt");
      setData(res.data);
      if (showToast) toast.success("Teknik borc güncellendi");
    } catch (err) {
      toast.error("Teknik borc yüklenemedi", { description: err.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-4" data-testid="tech-debt-loading">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 bg-zinc-800" />)}
        </div>
        <Skeleton className="h-48 bg-zinc-800" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-16 text-zinc-500" data-testid="tech-debt-empty">
        <Bug className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Teknik borc verisi bulunamadı</p>
      </div>
    );
  }

  const gradeStyle = GRADE_STYLES[data.health_grade] || GRADE_STYLES.D;

  return (
    <div className="space-y-6" data-testid="tech-debt-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Flame className="h-4 w-4 text-orange-400" />
          <span className="text-xs text-zinc-400 font-mono">
            Karantina Burn-Down Panosu
          </span>
        </div>
        <Button
          variant="ghost" size="sm" className="h-7 text-xs text-zinc-500"
          onClick={() => { setLoading(true); fetchData(true); }}
          data-testid="tech-debt-refresh"
        >
          <RefreshCw className="h-3 w-3 mr-1" />Yenile
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-4 w-4 text-orange-400" />
              <span className="text-xs text-zinc-500">Toplam Karantina</span>
            </div>
            <div className="text-2xl font-bold font-mono text-zinc-100" data-testid="debt-total-count">
              {data.total_quarantined}
            </div>
            <div className="text-[10px] text-zinc-600 mt-1 font-mono">{data.total_effort_hours} saat efor</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="h-4 w-4 text-blue-400" />
              <span className="text-xs text-zinc-500">Haftalik Hedef</span>
            </div>
            <div className="text-2xl font-bold font-mono text-zinc-100" data-testid="debt-weekly-target">
              {data.total_weekly_target}
            </div>
            <div className="text-[10px] text-zinc-600 mt-1 font-mono">test/hafta</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="h-4 w-4 text-yellow-400" />
              <span className="text-xs text-zinc-500">Sifira Kalan</span>
            </div>
            <div className="text-2xl font-bold font-mono text-zinc-100" data-testid="debt-weeks-remaining">
              {data.estimated_weeks_to_zero}
            </div>
            <div className="text-[10px] text-zinc-600 mt-1 font-mono">hafta</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="h-4 w-4 text-emerald-400" />
              <span className="text-xs text-zinc-500">Saglik Notu</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={`text-lg font-bold border px-3 py-1 ${gradeStyle}`} data-testid="debt-health-grade">
                {data.health_grade}
              </Badge>
              <span className="text-sm font-mono text-zinc-400">{data.health_score}/100</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Overall progress */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-zinc-500" /> Genel Ilerleme
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between text-xs text-zinc-500 mb-2">
            <span>0 test</span>
            <span className="font-mono">{data.total_quarantined} karantinada</span>
          </div>
          <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-red-500 via-orange-500 to-yellow-500 rounded-full transition-all duration-1000"
              style={{ width: `${Math.min((data.total_quarantined / 50) * 100, 100)}%` }}
              data-testid="debt-progress-bar"
            />
          </div>
          <div className="text-[10px] text-zinc-600 mt-2 font-mono">
            Hedef: Haftalik {data.total_weekly_target} test cozumu ile {data.estimated_weeks_to_zero} hafta icinde sifir
          </div>
        </CardContent>
      </Card>

      {/* Category breakdown */}
      <div>
        <h2 className="text-xs text-zinc-500 uppercase tracking-widest font-medium mb-3 flex items-center gap-2">
          <Bug className="h-3.5 w-3.5" /> Kategori Bazli Dagilim
        </h2>
        <div className="space-y-3" data-testid="debt-categories">
          {data.categories.map((cat) => (
            <CategoryCard key={cat.key} cat={cat} />
          ))}
        </div>
      </div>
    </div>
  );
}
