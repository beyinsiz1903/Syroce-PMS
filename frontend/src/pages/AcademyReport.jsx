import { useTranslation } from "react-i18next";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { ClipboardList, Users, CheckCircle2, Award, ArrowLeft, Loader2, UserPlus } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
const STATUS_META = {
  assigned: { intent: "info", label: "Atandi" },
  overdue: { intent: "danger", label: "Gecikmis" },
  completed: { intent: "success", label: "Tamamlandi" },
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
  const [options, setOptions] = useState({ users: [], courses: [] });
  const [assignment, setAssignment] = useState({ user_id: "", course_id: "", source: "manager", priority: "normal", required: true, due_at: "", reason: "" });
  const [assigning, setAssigning] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, optionResponse] = await Promise.all([axios.get("/academy/admin/report"), axios.get("/academy/admin/assignment-options")]);
      setData(r.data);
      setOptions(optionResponse.data || { users: [], courses: [] });
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);else toast.error("Rapor yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);
  const assignCourse = async () => {
    if (!assignment.user_id || !assignment.course_id) return toast.error("Personel ve egitim secin");
    if (assignment.source === "warning" && !assignment.reason.trim()) return toast.error("Telafi egitimi icin neden zorunludur");
    setAssigning(true);
    try {
      await axios.post("/academy/admin/assignments", { ...assignment, due_at: assignment.due_at ? `${assignment.due_at}T23:59:59Z` : null });
      toast.success("Egitim personele atandi");
      setAssignment(a => ({ ...a, course_id: "", reason: "" }));
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Egitim atanamadi");
    } finally { setAssigning(false); }
  };
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

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <KpiCard icon={Users} label={t("cm.pages_AcademyReport.kayit")} value={summary.enrollments || 0} intent="info" />
        <KpiCard icon={CheckCircle2} label={t("cm.pages_AcademyReport.gecen")} value={summary.passed || 0} intent="success" />
        <KpiCard icon={ClipboardList} label={t("cm.pages_AcademyReport.basari_orani")} value={`%${summary.pass_rate || 0}`} intent="neutral" />
        <KpiCard icon={Award} label={t("cm.pages_AcademyReport.sertifika")} value={summary.certificates || 0} intent="warning" />
        <KpiCard icon={ClipboardList} label="Gecikmis" value={summary.overdue || 0} intent={summary.overdue ? "danger" : "neutral"} />
      </div>

      <Card className="mb-6 overflow-hidden">
        <div className="border-b bg-slate-50 px-5 py-4">
          <div className="flex items-center gap-2 font-semibold text-slate-900"><UserPlus className="h-5 w-5 text-indigo-600" /> Personel egitim atamasi</div>
          <p className="mt-1 text-sm text-slate-500">Oryantasyon, yonetici talebi veya bir uyari sonrasi zorunlu telafi egitimi atayin.</p>
        </div>
        <div className="grid gap-3 p-5 md:grid-cols-2 lg:grid-cols-4">
          <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={assignment.user_id} onChange={e => setAssignment(a => ({ ...a, user_id: e.target.value }))}>
            <option value="">Personel secin</option>{options.users.map(u => <option key={u.id} value={u.id}>{u.name} · {u.role}</option>)}
          </select>
          <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={assignment.course_id} onChange={e => setAssignment(a => ({ ...a, course_id: e.target.value }))}>
            <option value="">Egitim secin</option>{options.courses.map(c => <option key={c.id} value={c.id}>{c.department_label} · {c.title}</option>)}
          </select>
          <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={assignment.source} onChange={e => setAssignment(a => ({ ...a, source: e.target.value, priority: e.target.value === "warning" ? "high" : a.priority }))}>
            <option value="manager">Yonetici atamasi</option><option value="onboarding">Oryantasyon</option><option value="warning">Uyari sonrasi telafi</option><option value="recertification">Yeniden belgelendirme</option>
          </select>
          <input type="date" className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={assignment.due_at} onChange={e => setAssignment(a => ({ ...a, due_at: e.target.value }))} aria-label="Son tarih" />
          <input className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm md:col-span-2 lg:col-span-3" placeholder={assignment.source === "warning" ? "Telafi nedeni (zorunlu)" : "Atama notu (istege bagli)"} value={assignment.reason} onChange={e => setAssignment(a => ({ ...a, reason: e.target.value }))} />
          <Button onClick={assignCourse} disabled={assigning}>{assigning && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Egitimi ata</Button>
        </div>
      </Card>

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
