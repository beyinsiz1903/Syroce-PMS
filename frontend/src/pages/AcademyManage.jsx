import { useTranslation } from "react-i18next";
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { GraduationCap, Plus, Pencil, Trash2, ArrowLeft, Loader2, BookOpen, FileText, Eye, EyeOff, Save, X, RotateCcw, PlayCircle } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { confirmDialog } from "@/lib/dialogs";

// Author roles MUST mirror backend ACADEMY_AUTHOR_ROLES exactly.
const AUTHOR_ROLES = new Set(["admin", "super_admin", "gm", "manager", "owner"]);

// Assignable course roles MUST mirror backend ACADEMY_COURSE_ROLES exactly.
const ROLE_OPTIONS = [{
  value: "front_desk",
  label: "On Buro"
}, {
  value: "housekeeping",
  label: "Kat Hizmetleri"
}, {
  value: "sales",
  label: "Satis"
}, {
  value: "finance",
  label: "Finans"
}, {
  value: "procurement",
  label: "Satin Alma"
}, {
  value: "staff",
  label: "Personel"
}, {
  value: "night_audit",
  label: "Gece Denetimi"
}, {
  value: "revenue",
  label: "Gelir Yonetimi"
}, {
  value: "supervisor",
  label: "Supervizor"
}, {
  value: "manager",
  label: "Mudur"
}, {
  value: "gm",
  label: "Genel Mudur"
}, {
  value: "owner",
  label: "Sahip"
}, {
  value: "admin",
  label: "Yonetici"
}, {
  value: "super_admin",
  label: "Super Yonetici"
}];
let _localSeq = 0;
const localId = prefix => `${prefix}-local-${Date.now()}-${_localSeq++}`;
const emptyLesson = () => ({
  id: localId("lesson"),
  title: "",
  body_markdown: ""
});
const emptyQuestion = () => ({
  id: localId("question"),
  prompt: "",
  options: ["", ""],
  answer_index: 0
});
const emptyCourse = () => ({
  title: "",
  department: "",
  department_label: "",
  summary: "",
  roles: [],
  draft: true,
  pass_threshold: 70,
  estimated_minutes: "",
  lessons: [emptyLesson()],
  questions: [emptyQuestion()]
});
export default function AcademyManage({
  user
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isAuthor = AUTHOR_ROLES.has(user?.role);
  const [loading, setLoading] = useState(false);
  const [courses, setCourses] = useState([]);
  const [systemCourses, setSystemCourses] = useState([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState(null); // null=create, else course id
  const [editKind, setEditKind] = useState("custom"); // "custom" | "system"
  const [form, setForm] = useState(emptyCourse());
  const [saving, setSaving] = useState(false);
  const isSystemEdit = editKind === "system";
  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([axios.get("/academy/admin/courses"), axios.get("/academy/admin/system-courses")]);
      setCourses(c.data?.items || []);
      setSystemCourses(s.data?.items || []);
    } catch (e) {
      toast.error("Akademi yonetimi yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (isAuthor) loadAll();
  }, [isAuthor, loadAll]);
  const openCreate = () => {
    setEditing(null);
    setEditKind("custom");
    setForm(emptyCourse());
    setEditorOpen(true);
  };
  const openEdit = async courseId => {
    setLoading(true);
    try {
      const r = await axios.get(`/academy/admin/courses/${courseId}`);
      const d = r.data || {};
      setForm({
        title: d.title || "",
        department: d.department || "",
        department_label: d.department_label || "",
        summary: d.summary || "",
        roles: Array.isArray(d.roles) ? d.roles : [],
        draft: !!d.draft,
        pass_threshold: d.pass_threshold ?? 70,
        estimated_minutes: d.estimated_minutes ?? "",
        lessons: (d.lessons || []).map(l => ({
          id: l.id || localId("lesson"),
          title: l.title || "",
          body_markdown: l.body_markdown || ""
        })),
        questions: (d.questions || []).map(q => ({
          id: q.id || localId("question"),
          prompt: q.prompt || "",
          options: Array.isArray(q.options) && q.options.length >= 2 ? [...q.options] : ["", ""],
          answer_index: typeof q.answer_index === "number" ? q.answer_index : 0
        }))
      });
      setEditing(courseId);
      setEditKind("custom");
      setEditorOpen(true);
    } catch (e) {
      toast.error("Kurs yuklenemedi");
    } finally {
      setLoading(false);
    }
  };
  const openSystemEdit = async courseId => {
    setLoading(true);
    try {
      const r = await axios.get(`/academy/admin/system-courses/${courseId}/content`);
      const d = r.data || {};
      setForm({
        title: d.title || "",
        department: d.department || "",
        department_label: d.department_label || "",
        summary: d.summary || "",
        roles: Array.isArray(d.roles) ? d.roles : [],
        draft: false,
        pass_threshold: d.pass_threshold ?? 70,
        estimated_minutes: d.estimated_minutes ?? "",
        lessons: (d.lessons || []).map(l => ({
          id: l.id || localId("lesson"),
          title: l.title || "",
          body_markdown: l.body_markdown || ""
        })),
        questions: (d.questions || []).map(q => ({
          id: q.id || localId("question"),
          prompt: q.prompt || "",
          options: Array.isArray(q.options) && q.options.length >= 2 ? [...q.options] : ["", ""],
          answer_index: typeof q.answer_index === "number" ? q.answer_index : 0
        }))
      });
      setEditing(courseId);
      setEditKind("system");
      setEditorOpen(true);
    } catch (e) {
      toast.error("Hazir egitim yuklenemedi");
    } finally {
      setLoading(false);
    }
  };
  const toggleRole = role => {
    setForm(f => ({
      ...f,
      roles: f.roles.includes(role) ? f.roles.filter(r => r !== role) : [...f.roles, role]
    }));
  };

  // ---- lessons ----
  const addLesson = () => setForm(f => ({
    ...f,
    lessons: [...f.lessons, emptyLesson()]
  }));
  const removeLesson = id => setForm(f => ({
    ...f,
    lessons: f.lessons.filter(l => l.id !== id)
  }));
  const updateLesson = (id, key, val) => setForm(f => ({
    ...f,
    lessons: f.lessons.map(l => l.id === id ? {
      ...l,
      [key]: val
    } : l)
  }));

  // ---- questions ----
  const addQuestion = () => setForm(f => ({
    ...f,
    questions: [...f.questions, emptyQuestion()]
  }));
  const removeQuestion = id => setForm(f => ({
    ...f,
    questions: f.questions.filter(q => q.id !== id)
  }));
  const updateQuestion = (id, key, val) => setForm(f => ({
    ...f,
    questions: f.questions.map(q => q.id === id ? {
      ...q,
      [key]: val
    } : q)
  }));
  const addOption = qid => setForm(f => ({
    ...f,
    questions: f.questions.map(q => q.id === qid && q.options.length < 8 ? {
      ...q,
      options: [...q.options, ""]
    } : q)
  }));
  const removeOption = (qid, oi) => setForm(f => ({
    ...f,
    questions: f.questions.map(q => {
      if (q.id !== qid || q.options.length <= 2) return q;
      const options = q.options.filter((_, i) => i !== oi);
      let answer_index = q.answer_index;
      if (oi === answer_index) answer_index = 0;else if (oi < answer_index) answer_index -= 1;
      return {
        ...q,
        options,
        answer_index
      };
    })
  }));
  const updateOption = (qid, oi, val) => setForm(f => ({
    ...f,
    questions: f.questions.map(q => q.id === qid ? {
      ...q,
      options: q.options.map((o, i) => i === oi ? val : o)
    } : q)
  }));
  const validate = () => {
    if (!form.title.trim()) return "Kurs basligi gerekli";
    if (!form.roles.length) return "En az bir rol secin";
    const pt = Number(form.pass_threshold);
    if (!Number.isFinite(pt) || pt < 1 || pt > 100) return "Gecme notu 1-100 arasinda olmali";
    // Built-in content overrides always need >=1 lesson and >=1 question
    // (no draft escape hatch); custom courses only when publishing.
    if (isSystemEdit || !form.draft) {
      if (!form.lessons.length) return "En az 1 ders gerekli";
      if (!form.questions.length) return "En az 1 soru gerekli";
    }
    for (const l of form.lessons) {
      if (!l.title.trim()) return "Tum derslerin basligi olmali";
    }
    for (const q of form.questions) {
      if (!q.prompt.trim()) return "Tum sorularin metni olmali";
      const opts = q.options.map(o => o.trim());
      if (opts.length < 2) return "Her soruda en az 2 secenek olmali";
      if (opts.some(o => !o)) return "Secenekler bos olamaz";
      if (q.answer_index < 0 || q.answer_index >= opts.length) {
        return "Her soruda gecerli bir dogru cevap secin";
      }
    }
    return null;
  };
  const buildPayload = () => {
    const payload = {
      title: form.title.trim(),
      department: form.department.trim() || null,
      department_label: form.department_label.trim() || null,
      summary: form.summary.trim(),
      roles: form.roles,
      draft: form.draft,
      pass_threshold: Number(form.pass_threshold),
      estimated_minutes: form.estimated_minutes === "" || form.estimated_minutes === null ? null : Number(form.estimated_minutes),
      // Preserve real (server-issued) lesson/question ids on edit so in-flight
      // learner progress (keyed by lesson id) survives; locally-added items send
      // null so the engine mints a clean id.
      lessons: form.lessons.map(l => ({
        id: l.id && !l.id.includes("-local-") ? l.id : null,
        title: l.title.trim(),
        body_markdown: l.body_markdown
      })),
      questions: form.questions.map(q => ({
        id: q.id && !q.id.includes("-local-") ? q.id : null,
        prompt: q.prompt.trim(),
        options: q.options.map(o => o.trim()),
        answer_index: q.answer_index
      }))
    };
    // Built-in content has no draft concept — strip it so the stricter
    // SystemCourseContentInput schema receives exactly what it expects.
    if (isSystemEdit) delete payload.draft;
    return payload;
  };
  const save = async () => {
    const err = validate();
    if (err) {
      toast.error(err);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload();
      if (isSystemEdit) {
        await axios.put(`/academy/admin/system-courses/${editing}/content`, payload);
        toast.success("Hazir egitim guncellendi");
      } else if (editing) {
        await axios.put(`/academy/admin/courses/${editing}`, payload);
        toast.success("Kurs guncellendi");
      } else {
        await axios.post("/academy/admin/courses", payload);
        toast.success("Kurs olusturuldu");
      }
      setEditorOpen(false);
      await loadAll();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Kurs kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };
  const removeCourse = async course => {
    const ok = await confirmDialog({
      title: "Kursu sil",
      description: `"${course.title}" kalici olarak silinecek. Bu islem geri alinamaz.`,
      confirmText: "Sil",
      cancelText: "Vazgec",
      destructive: true
    });
    if (!ok) return;
    try {
      await axios.delete(`/academy/admin/courses/${course.id}`);
      toast.success("Kurs silindi");
      await loadAll();
    } catch (e) {
      toast.error("Kurs silinemedi");
    }
  };
  const toggleSystemVisibility = async course => {
    const nextHidden = !course.hidden;
    // Optimistic flip; revert on failure.
    setSystemCourses(prev => prev.map(c => c.id === course.id ? {
      ...c,
      hidden: nextHidden
    } : c));
    try {
      await axios.put(`/academy/admin/system-courses/${course.id}/visibility`, {
        hidden: nextHidden
      });
    } catch (e) {
      setSystemCourses(prev => prev.map(c => c.id === course.id ? {
        ...c,
        hidden: !nextHidden
      } : c));
      toast.error("Gorunurluk degistirilemedi");
    }
  };
  const resetSystemCourse = async course => {
    const ok = await confirmDialog({
      title: "Varsayilana sifirla",
      description: `"${course.title}" egitiminin otelinize ozel icerigi silinip varsayilan (hazir) icerik geri yuklenecek. Gizleme ayari korunur. Bu islem geri alinamaz.`,
      confirmText: "Sifirla",
      cancelText: "Vazgec",
      destructive: true
    });
    if (!ok) return;
    try {
      await axios.delete(`/academy/admin/system-courses/${course.id}/content`);
      toast.success("Hazir egitim varsayilana sifirlandi");
      await loadAll();
    } catch (e) {
      toast.error("Sifirlama basarisiz");
    }
  };
  if (!isAuthor) {
    return <div className="p-4 md:p-6 max-w-5xl mx-auto">
        <Card className="p-8 text-center text-slate-500">{t("cm.pages_AcademyManage.bu_sayfa_icin_yetkiniz_yok")}</Card>
      </div>;
  }
  const publishedCount = courses.filter(c => !c.draft).length;
  const hiddenSystemCount = systemCourses.filter(c => c.hidden).length;
  if (loading && courses.length === 0 && systemCourses.length === 0) {
    return <div className="flex items-center justify-center py-24 text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />{t("cm.pages_AcademyManage.yukleniyor")}</div>;
  }
  return <div className="p-4 md:p-6 max-w-5xl mx-auto">
      <PageHeader title={t("cm.pages_AcademyManage.akademi_yonetimi")} subtitle="Otelinize ozel egitimler olusturun, duzenleyin ve hazir egitimleri gizleyin/gosterin." actions={<div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate("/app/academy")}>
              <ArrowLeft className="w-4 h-4 mr-2" />{t("cm.pages_AcademyManage.akademiye_don")}</Button>
            <Button onClick={openCreate}>
              <Plus className="w-4 h-4 mr-2" />{t("cm.pages_AcademyManage.yeni_kurs")}</Button>
          </div>} />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <KpiCard icon={BookOpen} label={t("cm.pages_AcademyManage.ozel_egitim")} value={courses.length} intent="info" />
        <KpiCard icon={GraduationCap} label={t("cm.pages_AcademyManage.yayinda")} value={publishedCount} intent="success" />
        <KpiCard icon={EyeOff} label={t("cm.pages_AcademyManage.gizli_hazir_egitim")} value={hiddenSystemCount} intent="warning" />
      </div>

      <h2 className="text-lg font-bold text-slate-900 mb-3">{t("cm.pages_AcademyManage.ozel_egitimler")}</h2>
      {courses.length === 0 ? <Card className="p-8 text-center text-slate-500">{t("cm.pages_AcademyManage.henuz_ozel_egitim_olusturmadin")}</Card> : <div className="space-y-3">
          {courses.map(c => <Card key={c.id} className="p-4 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <GraduationCap className="w-5 h-5 text-slate-700 flex-shrink-0" />
                  <h3 className="font-semibold text-slate-900">{c.title}</h3>
                  {c.draft ? <StatusBadge intent="warning">{t("cm.pages_AcademyManage.taslak")}</StatusBadge> : <StatusBadge intent="success">{t("cm.pages_AcademyManage.yayinda")}</StatusBadge>}
                </div>
                <p className="text-sm text-slate-500 mt-1">{c.summary}</p>
                <div className="text-xs text-slate-400 mt-2">
                  {c.department_label || c.department || "Genel"} · {c.lesson_count}{t("cm.pages_AcademyManage.ders")}{c.question_count}{t("cm.pages_AcademyManage.soru_gecme_notu")}{c.pass_threshold}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Button size="sm" variant="outline" onClick={() => openEdit(c.id)}>
                  <Pencil className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.duzenle")}</Button>
                <Button size="sm" variant="outline" onClick={() => removeCourse(c)}>
                  <Trash2 className="w-4 h-4 text-rose-600" />
                </Button>
              </div>
            </Card>)}
        </div>}

      <h2 className="text-lg font-bold text-slate-900 mb-3 mt-8">{t("cm.pages_AcademyManage.hazir_egitimler")}</h2>
      <p className="text-sm text-slate-500 mb-3">{t("cm.pages_AcademyManage.hazir_egitimler_tum_oteller_ic")}</p>
      <div className="space-y-2">
        {systemCourses.map(c => <Card key={c.id} className="p-4 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <FileText className="w-5 h-5 text-slate-600 flex-shrink-0" />
                <h3 className="font-medium text-slate-900">{c.title}</h3>
                {c.customized && <StatusBadge intent="info">{t("cm.pages_AcademyManage.ozellestirildi")}</StatusBadge>}
                {c.hidden && <StatusBadge intent="neutral">{t("cm.pages_AcademyManage.gizli")}</StatusBadge>}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                {c.department_label || c.department || "Genel"} · {c.lesson_count}{t("cm.pages_AcademyManage.ders")}{c.question_count}{t("cm.pages_AcademyManage.soru")}</div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Button size="sm" variant="outline" onClick={() => openSystemEdit(c.id)}>
                <Pencil className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.duzenle")}</Button>
              {c.customized && <Button size="sm" variant="outline" onClick={() => resetSystemCourse(c)}>
                  <RotateCcw className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.varsayilana_sifirla")}</Button>}
              <Button size="sm" variant="outline" onClick={() => toggleSystemVisibility(c)}>
                {c.hidden ? <><Eye className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.goster")}</> : <><EyeOff className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.gizle")}</>}
              </Button>
            </div>
          </Card>)}
      </div>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {isSystemEdit ? "Hazir Egitimi Duzenle" : editing ? "Kursu Duzenle" : "Yeni Kurs"}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-5">
            {/* Meta */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label htmlFor="ac-title">{t("cm.pages_AcademyManage.baslik")}</Label>
                <Input id="ac-title" value={form.title} onChange={e => setForm(f => ({
                ...f,
                title: e.target.value
              }))} placeholder={t("cm.pages_AcademyManage.orn_resepsiyon_karsilama_stand")} />
              </div>
              <div>
                <Label htmlFor="ac-dep">{t("cm.pages_AcademyManage.departman_anahtar")}</Label>
                <Input id="ac-dep" value={form.department} onChange={e => setForm(f => ({
                ...f,
                department: e.target.value
              }))} placeholder={t("cm.pages_AcademyManage.front_desk")} />
              </div>
              <div>
                <Label htmlFor="ac-deplabel">{t("cm.pages_AcademyManage.departman_etiketi")}</Label>
                <Input id="ac-deplabel" value={form.department_label} onChange={e => setForm(f => ({
                ...f,
                department_label: e.target.value
              }))} placeholder={t("cm.pages_AcademyManage.on_buro")} />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="ac-summary">{t("cm.pages_AcademyManage.ozet")}</Label>
                <Textarea id="ac-summary" value={form.summary} onChange={e => setForm(f => ({
                ...f,
                summary: e.target.value
              }))} rows={2} />
              </div>
              <div>
                <Label htmlFor="ac-threshold">{t("cm.pages_AcademyManage.gecme_notu_1_100")}</Label>
                <Input id="ac-threshold" type="number" min={1} max={100} value={form.pass_threshold} onChange={e => setForm(f => ({
                ...f,
                pass_threshold: e.target.value
              }))} />
              </div>
              <div>
                <Label htmlFor="ac-minutes">{t("cm.pages_AcademyManage.tahmini_sure_dk")}</Label>
                <Input id="ac-minutes" type="number" min={0} value={form.estimated_minutes} onChange={e => setForm(f => ({
                ...f,
                estimated_minutes: e.target.value
              }))} placeholder={t("cm.pages_AcademyManage.opsiyonel")} />
              </div>
            </div>

            {/* Roles */}
            <div>
              <Label>{t("cm.pages_AcademyManage.atanacak_roller")}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {ROLE_OPTIONS.map(r => {
                const on = form.roles.includes(r.value);
                return <button key={r.value} type="button" onClick={() => toggleRole(r.value)} className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${on ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"}`}>
                      {r.label}
                    </button>;
              })}
              </div>
            </div>

            {/* Draft toggle — built-in content has no draft concept */}
            {!isSystemEdit && <div className="flex items-center justify-between rounded border border-slate-200 px-3 py-2">
                <div>
                  <div className="text-sm font-medium text-slate-900">{t("cm.pages_AcademyManage.taslak")}</div>
                  <div className="text-xs text-slate-400">{t("cm.pages_AcademyManage.taslak_egitimler_ogrencilere_g")}</div>
                </div>
                <Switch checked={form.draft} onCheckedChange={v => setForm(f => ({
              ...f,
              draft: v
            }))} />
              </div>}

            {/* Lessons */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-slate-900">{t("cm.pages_AcademyManage.dersler")}</h3>
                <Button size="sm" variant="outline" onClick={addLesson}>
                  <Plus className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.ders_ekle")}</Button>
              </div>
              <div className="space-y-3">
                {form.lessons.map((l, li) => <Card key={l.id} className="p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs text-slate-400 w-6">{li + 1}.</span>
                      <Input value={l.title} onChange={e => updateLesson(l.id, "title", e.target.value)} placeholder={t("cm.pages_AcademyManage.ders_basligi")} />
                      <Button size="sm" variant="outline" onClick={() => removeLesson(l.id)} disabled={form.lessons.length <= 1}>
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                    <div className="flex items-center justify-between mt-2 mb-1">
                      <label className="text-xs font-semibold text-slate-700">Ders İçeriği</label>
                      <div className="flex items-center gap-2">
                        <Button type="button" size="sm" variant="secondary" className="h-6 text-[10px] px-2" onClick={() => {
                          const url = window.prompt("YouTube Video Linki veya ID'sini girin:\nÖrn: https://youtube.com/watch?v=dQw4w9WgXcQ");
                          if (!url) return;
                          let id = url;
                          const m = url.match(/(?:v=|youtu\.be\/|embed\/)([^&?]+)/);
                          if (m) id = m[1];
                          updateLesson(l.id, "body_markdown", (l.body_markdown || "") + `\n\n@[youtube](${id})\n`);
                        }}>
                          <PlayCircle className="w-3 h-3 mr-1" /> YouTube Ekle
                        </Button>
                        <Button type="button" size="sm" variant="secondary" className="h-6 text-[10px] px-2" onClick={() => {
                          const url = window.prompt("Vimeo Video Linki veya ID'sini girin:");
                          if (!url) return;
                          let id = url;
                          const m = url.match(/vimeo\.com\/(\d+)/);
                          if (m) id = m[1];
                          updateLesson(l.id, "body_markdown", (l.body_markdown || "") + `\n\n@[vimeo](${id})\n`);
                        }}>
                          <PlayCircle className="w-3 h-3 mr-1" /> Vimeo Ekle
                        </Button>
                      </div>
                    </div>
                    <Textarea value={l.body_markdown} onChange={e => updateLesson(l.id, "body_markdown", e.target.value)} rows={5} placeholder={t("cm.pages_AcademyManage.ders_icerigi_markdown_destekli")} className="font-mono text-xs border-slate-200" />
                  </Card>)}
              </div>
            </div>

            {/* Questions */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-slate-900">{t("cm.pages_AcademyManage.sinav_sorulari")}</h3>
                <Button size="sm" variant="outline" onClick={addQuestion}>
                  <Plus className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.soru_ekle")}</Button>
              </div>
              <div className="space-y-3">
                {form.questions.map((q, qi) => <Card key={q.id} className="p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs text-slate-400 w-6">{qi + 1}.</span>
                      <Input value={q.prompt} onChange={e => updateQuestion(q.id, "prompt", e.target.value)} placeholder={t("cm.pages_AcademyManage.soru_metni")} />
                      <Button size="sm" variant="outline" onClick={() => removeQuestion(q.id)} disabled={form.questions.length <= 1}>
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                    <div className="space-y-2 pl-8">
                      {q.options.map((opt, oi) => <div key={oi} className="flex items-center gap-2">
                          <input type="radio" name={`answer-${q.id}`} checked={q.answer_index === oi} onChange={() => updateQuestion(q.id, "answer_index", oi)} title={t("cm.pages_AcademyManage.dogru_cevap")} />
                          <Input value={opt} onChange={e => updateOption(q.id, oi, e.target.value)} placeholder={`Secenek ${oi + 1}`} />
                          <Button size="sm" variant="outline" onClick={() => removeOption(q.id, oi)} disabled={q.options.length <= 2}>
                            <X className="w-4 h-4" />
                          </Button>
                        </div>)}
                      <Button size="sm" variant="ghost" onClick={() => addOption(q.id)} disabled={q.options.length >= 8}>
                        <Plus className="w-4 h-4 mr-1" />{t("cm.pages_AcademyManage.secenek_ekle")}</Button>
                      <div className="text-xs text-slate-400">{t("cm.pages_AcademyManage.dogru_cevabi_soldaki_secenek_d")}</div>
                    </div>
                  </Card>)}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditorOpen(false)} disabled={saving}>{t("cm.pages_AcademyManage.vazgec")}</Button>
            <Button onClick={save} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              <Save className="w-4 h-4 mr-2" />{t("cm.pages_AcademyManage.kaydet")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>;
}