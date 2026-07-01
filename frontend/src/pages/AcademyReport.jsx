import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import {
  ClipboardList, Users, CheckCircle2, Award, ArrowLeft, Loader2,
} from "lucide-react";

import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const STATUS_META = {
  not_started: { intent: "neutral", label: "Baslanmadi" },
  in_progress: { intent: "info", label: "Devam ediyor" },
  passed: { intent: "success", label: "Gecti" },
  failed: { intent: "danger", label: "Kaldi" },
};

export default function AcademyReport() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get("/academy/admin/report");
      setData(r.data);
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);
      else toast.error("Rapor yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" /> Yukleniyor...
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <Card className="p-8 text-center text-slate-500">
          Bu rapor icin yetkiniz bulunmuyor.
          <div className="mt-4">
            <Button variant="outline" onClick={() => navigate("/app/academy")}>
              <ArrowLeft className="w-4 h-4 mr-2" /> Akademiye Don
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const summary = data?.summary || {};
  const departments = data?.departments || [];
  const rows = data?.rows || [];

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <PageHeader
        title="Akademi Yonetici Raporu"
        subtitle="Departman ve personel bazinda egitim tamamlama, basari ve puanlar."
        actions={(
          <Button variant="outline" onClick={() => navigate("/app/academy")}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Akademi
          </Button>
        )}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <KpiCard icon={Users} label="Kayit" value={summary.enrollments || 0} intent="info" />
        <KpiCard icon={CheckCircle2} label="Gecen" value={summary.passed || 0} intent="success" />
        <KpiCard icon={ClipboardList} label="Basari Orani" value={`%${summary.pass_rate || 0}`} intent="neutral" />
        <KpiCard icon={Award} label="Sertifika" value={summary.certificates || 0} intent="warning" />
      </div>

      {departments.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-bold text-slate-900 mb-3">Departman Ozeti</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {departments.map((d) => (
              <Card key={d.department_label} className="p-4">
                <div className="font-semibold text-slate-900">{d.department_label}</div>
                <div className="text-sm text-slate-500 mt-1">
                  {d.passed} / {d.enrollments} gecti
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      <h2 className="text-lg font-bold text-slate-900 mb-3">Personel Detayi</h2>
      {rows.length === 0 ? (
        <Card className="p-8 text-center text-slate-500">
          Henuz egitim kaydi bulunmuyor.
        </Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="px-4 py-3 font-medium">Personel</th>
                <th className="px-4 py-3 font-medium">Departman</th>
                <th className="px-4 py-3 font-medium">Egitim</th>
                <th className="px-4 py-3 font-medium">Ilerleme</th>
                <th className="px-4 py-3 font-medium">Durum</th>
                <th className="px-4 py-3 font-medium">En Iyi Puan</th>
                <th className="px-4 py-3 font-medium">Sertifika</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => {
                const meta = STATUS_META[r.status] || STATUS_META.not_started;
                return (
                  <tr key={`${r.user_id}-${r.course_id}-${idx}`} className="border-b last:border-0">
                    <td className="px-4 py-3 text-slate-900">{r.user_name}</td>
                    <td className="px-4 py-3 text-slate-600">{r.department_label}</td>
                    <td className="px-4 py-3 text-slate-600">{r.course_title}</td>
                    <td className="px-4 py-3 text-slate-600">{r.lessons_completed}/{r.lesson_count}</td>
                    <td className="px-4 py-3"><StatusBadge intent={meta.intent}>{meta.label}</StatusBadge></td>
                    <td className="px-4 py-3 text-slate-600">{r.best_score}</td>
                    <td className="px-4 py-3">{r.has_certificate ? "Evet" : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
