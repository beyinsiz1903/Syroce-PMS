import { useTranslation } from "react-i18next";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { ClipboardList, Users, CheckCircle2, Award, ArrowLeft, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
const STATUS_META = {
  not_started: {
    intent: "neutral",
    label: "Baslanmadi"
  },
  in_progress: {
    intent: "info",
    label: "Devam ediyor"
  },
  passed: {
    intent: "success",
    label: "Gecti"
  },
  failed: {
    intent: "danger",
    label: "Kaldi"
  }
};
export default function AcademyReport() {
  const { t } = useTranslation();
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
      if (e?.response?.status === 403) setForbidden(true);else toast.error("Rapor yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (loading) {
    return <div className="flex items-center justify-center py-24 text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />{t("cm.pages_AcademyReport.yukleniyor")}</div>;
  }
  if (forbidden) {
    return <div className="p-6 max-w-3xl mx-auto">
        <Card className="p-8 text-center text-slate-500">{t("cm.pages_AcademyReport.bu_rapor_icin_yetkiniz_bulunmu")}<div className="mt-4">
            <Button variant="outline" onClick={() => navigate("/app/academy")}>
              <ArrowLeft className="w-4 h-4 mr-2" />{t("cm.pages_AcademyReport.akademiye_don")}</Button>
          </div>
        </Card>
      </div>;
  }
  const summary = data?.summary || {};
  const departments = data?.departments || [];
  const rows = data?.rows || [];
  return <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <PageHeader title={t("cm.pages_AcademyReport.akademi_yonetici_raporu")} subtitle="Departman ve personel bazinda egitim tamamlama, basari ve puanlar." actions={<Button variant="outline" onClick={() => navigate("/app/academy")}>
            <ArrowLeft className="w-4 h-4 mr-2" />{t("cm.pages_AcademyReport.akademi")}</Button>} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <KpiCard icon={Users} label={t("cm.pages_AcademyReport.kayit")} value={summary.enrollments || 0} intent="info" />
        <KpiCard icon={CheckCircle2} label={t("cm.pages_AcademyReport.gecen")} value={summary.passed || 0} intent="success" />
        <KpiCard icon={ClipboardList} label={t("cm.pages_AcademyReport.basari_orani")} value={`%${summary.pass_rate || 0}`} intent="neutral" />
        <KpiCard icon={Award} label={t("cm.pages_AcademyReport.sertifika")} value={summary.certificates || 0} intent="warning" />
      </div>

      {departments.length > 0 && <div className="mb-6">
          <h2 className="text-lg font-bold text-slate-900 mb-3">{t("cm.pages_AcademyReport.departman_ozeti")}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {departments.map(d => <Card key={d.department_label} className="p-4">
                <div className="font-semibold text-slate-900">{d.department_label}</div>
                <div className="text-sm text-slate-500 mt-1">
                  {d.passed} / {d.enrollments}{t("cm.pages_AcademyReport.gecti")}</div>
              </Card>)}
          </div>
        </div>}

      <h2 className="text-lg font-bold text-slate-900 mb-3">{t("cm.pages_AcademyReport.personel_detayi")}</h2>
      {rows.length === 0 ? <Card className="p-8 text-center text-slate-500">{t("cm.pages_AcademyReport.henuz_egitim_kaydi_bulunmuyor")}</Card> : <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.personel")}</th>
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.departman")}</th>
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.egitim")}</th>
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.ilerleme")}</th>
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.durum")}</th>
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.en_iyi_puan")}</th>
                <th className="px-4 py-3 font-medium">{t("cm.pages_AcademyReport.sertifika")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => {
            const meta = STATUS_META[r.status] || STATUS_META.not_started;
            return <tr key={`${r.user_id}-${r.course_id}-${idx}`} className="border-b last:border-0">
                    <td className="px-4 py-3 text-slate-900">{r.user_name}</td>
                    <td className="px-4 py-3 text-slate-600">{r.department_label}</td>
                    <td className="px-4 py-3 text-slate-600">{r.course_title}</td>
                    <td className="px-4 py-3 text-slate-600">{r.lessons_completed}/{r.lesson_count}</td>
                    <td className="px-4 py-3"><StatusBadge intent={meta.intent}>{meta.label}</StatusBadge></td>
                    <td className="px-4 py-3 text-slate-600">{r.best_score}</td>
                    <td className="px-4 py-3">{r.has_certificate ? "Evet" : "—"}</td>
                  </tr>;
          })}
            </tbody>
          </table>
        </Card>}
    </div>;
}