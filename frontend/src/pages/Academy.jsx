import { t } from "i18next";
import { useCallback, useEffect, useState } from "react";
import DOMPurify from "dompurify";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { GraduationCap, BookOpen, Award, CheckCircle2, ArrowLeft, FileText, Loader2, Download, ClipboardList, Settings2, Lock, Building2, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
const MANAGER_ROLES = new Set(["admin", "super_admin", "supervisor", "gm", "manager", "owner"]);

// Author roles MUST mirror backend ACADEMY_AUTHOR_ROLES (excludes supervisor).
const AUTHOR_ROLES = new Set(["admin", "super_admin", "gm", "manager", "owner"]);
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

// Minimal Markdown renderer for lesson bodies (headings, bold, lists, tables,
// blockquote, paragraphs). No external dependency.
function renderMarkdown(src) {
  if (!src) return {
    __html: ""
  };
  const escape = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = s => escape(s).replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-gray-100 rounded text-xs font-mono">$1</code>').replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    let m;
    m = ln.match(/^###\s+(.*)$/);
    if (m) {
      out.push(`<h3 class="text-base font-semibold mt-5 mb-2">${inline(m[1])}</h3>`);
      i++;
      continue;
    }
    m = ln.match(/^##\s+(.*)$/);
    if (m) {
      out.push(`<h2 class="text-lg font-bold mt-6 mb-2">${inline(m[1])}</h2>`);
      i++;
      continue;
    }
    m = ln.match(/^#\s+(.*)$/);
    if (m) {
      out.push(`<h1 class="text-2xl font-bold mt-2 mb-3">${inline(m[1])}</h1>`);
      i++;
      continue;
    }
    if (/^>\s?/.test(ln)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      out.push(`<blockquote class="border-l-4 border-amber-300 bg-amber-50 pl-3 py-2 my-3 text-sm text-amber-900">${inline(buf.join(" "))}</blockquote>`);
      continue;
    }
    if (/^---+\s*$/.test(ln)) {
      out.push('<hr class="my-4 border-gray-200" />');
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(ln)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(`<li class="ml-6 list-disc my-1">${inline(lines[i].replace(/^\s*[-*]\s+/, ""))}</li>`);
        i++;
      }
      out.push(`<ul class="my-2">${items.join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(ln)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(`<li class="ml-6 list-decimal my-1">${inline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        i++;
      }
      out.push(`<ol class="my-2">${items.join("")}</ol>`);
      continue;
    }
    if (/^\|/.test(ln)) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        rows.push(lines[i]);
        i++;
      }
      const html = rows.map((r, idx) => {
        if (/^\|[\s:-]+\|/.test(r)) return "";
        const cells = r.split("|").slice(1, -1).map(c => `<td class="border px-3 py-1.5 text-sm">${inline(c.trim())}</td>`).join("");
        const tag = idx === 0 ? "th" : "td";
        const replaced = cells.replace(/<td/g, `<${tag}`).replace(/<\/td>/g, `</${tag}>`);
        return `<tr>${replaced}</tr>`;
      }).join("");
      out.push(`<table class="border-collapse border my-3"><tbody>${html}</tbody></table>`);
      continue;
    }
    if (ln.trim() === "") {
      i++;
      continue;
    }
    const buf = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^[#`|>]|^\s*[-*\d]\s+|^---+/.test(lines[i])) {
      buf.push(lines[i]);
      i++;
    }
    out.push(`<p class="my-2 leading-relaxed text-sm text-gray-800">${inline(buf.join(" "))}</p>`);
  }
  // XSS guard: even though the markdown renderer above HTML-escapes raw input
  // before interpolation, a final DOMPurify pass ensures any edge-cases
  // (e.g. crafted attribute injection, mXSS via browser HTML parser) are blocked.
  return {
    __html: DOMPurify.sanitize(out.join("\n"), {
      USE_PROFILES: {
        html: true
      }
    })
  };
}
export default function Academy({
  user
}) {
  const navigate = useNavigate();
  const [view, setView] = useState("list");
  const [loading, setLoading] = useState(false);
  const [courses, setCourses] = useState([]);
  const [certificates, setCertificates] = useState([]);
  const [course, setCourse] = useState(null);
  const [exam, setExam] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  // Yukleme reddini turune gore ayirir: modul kapali / otel baglami yok /
  // gecici hata. Bu sayede kirmizi alarm yerine duruma uygun mesaj gosterilir.
  const [loadError, setLoadError] = useState(null);
  const isManager = MANAGER_ROLES.has(user?.role);
  const isAuthor = AUTHOR_ROLES.has(user?.role);
  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const [c, certs] = await Promise.all([axios.get("/academy/courses"), axios.get("/academy/certificates")]);
      setCourses(c.data?.items || []);
      setCertificates(certs.data?.items || []);
      setLoadError(null);
    } catch (e) {
      const status = e?.response?.status;
      const code = e?.response?.data?.error_code;
      const detail = e?.response?.data?.detail || "";
      let type;
      if (status === 403 && code === "ENTITLEMENT_DENIED") {
        // Academy ek modulu bu otelde etkin degil.
        type = "module_disabled";
      } else if (status === 403 && /otel hesab/i.test(detail)) {
        // Otel baglami olmayan ( or. super-admin) oturum.
        type = "no_tenant";
      } else {
        // Ag/sunucu kaynakli gecici hata.
        type = "transient";
      }
      setCourses([]);
      setCertificates([]);
      setLoadError(type);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    loadList();
  }, [loadList]);
  const openCourse = async courseId => {
    setLoading(true);
    try {
      const r = await axios.get(`/academy/courses/${courseId}`);
      setCourse(r.data);
      setView("course");
    } catch (e) {
      toast.error("Kurs yuklenemedi");
    } finally {
      setLoading(false);
    }
  };
  const completeLesson = async lessonId => {
    if (!course) return;
    try {
      const r = await axios.post(`/academy/courses/${course.id}/lessons/${lessonId}/complete`);
      setCourse(prev => ({
        ...prev,
        progress: {
          ...prev.progress,
          completed_lessons: r.data?.completed_lessons || []
        }
      }));
    } catch (e) {
      toast.error("Ders tamamlanamadi");
    }
  };
  const startExam = async () => {
    if (!course) return;
    setLoading(true);
    try {
      const r = await axios.get(`/academy/courses/${course.id}/exam`);
      setExam(r.data);
      setAnswers({});
      setResult(null);
      setView("exam");
    } catch (e) {
      toast.error("Sinav yuklenemedi");
    } finally {
      setLoading(false);
    }
  };
  const submitExam = async () => {
    if (!exam || !course) return;
    if (Object.keys(answers).length < (exam.questions?.length || 0)) {
      toast.error("Lutfen tum sorulari yanitlayin");
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(`/academy/courses/${course.id}/exam/submit`, {
        answers
      });
      setResult(r.data);
      setView("result");
      await loadList();
    } catch (e) {
      toast.error("Sinav gonderilemedi");
    } finally {
      setSubmitting(false);
    }
  };
  const downloadCertificate = async (certId, code) => {
    try {
      const r = await axios.get(`/academy/certificates/${certId}/pdf`, {
        responseType: "blob"
      });
      const url = window.URL.createObjectURL(new Blob([r.data], {
        type: "application/pdf"
      }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `sertifika-${code || certId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Sertifika indirilemedi");
    }
  };
  const backToList = () => {
    setView("list");
    setCourse(null);
    setExam(null);
    setResult(null);
  };

  // KPI summary
  const totalCourses = courses.length;
  const passedCourses = courses.filter(c => c.progress?.passed).length;
  const certCount = certificates.length;
  if (loading && view === "list" && courses.length === 0) {
    return <div className="flex items-center justify-center py-24 text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />{t("cm.pages_Academy.yukleniyor")}</div>;
  }
  const renderLoadErrorState = () => {
    if (loadError === "module_disabled") {
      return <Card className="p-10 text-center">
          <Lock className="w-10 h-10 text-slate-400 mx-auto mb-4" />
          <h3 className="font-semibold text-slate-900 mb-1">{t("cm.pages_Academy.syroce_academy_bu_otelde_etkin")}</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">{t("cm.pages_Academy.syroce_academy_ek_bir_moduldur")}</p>
        </Card>;
    }
    if (loadError === "no_tenant") {
      return <Card className="p-10 text-center">
          <Building2 className="w-10 h-10 text-slate-400 mx-auto mb-4" />
          <h3 className="font-semibold text-slate-900 mb-1">{t("cm.pages_Academy.otel_hesabi_gerekli")}</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">{t("cm.pages_Academy.academy_icerigi_otele_baglidir")}</p>
        </Card>;
    }
    // transient
    return <Card className="p-10 text-center">
        <RefreshCw className="w-10 h-10 text-slate-400 mx-auto mb-4" />
        <h3 className="font-semibold text-slate-900 mb-1">{t("cm.pages_Academy.academy_icerigi_su_anda_yuklen")}</h3>
        <p className="text-sm text-slate-500 max-w-md mx-auto mb-5">{t("cm.pages_Academy.gecici_bir_sorun_olustu_lutfen")}</p>
        <Button variant="outline" onClick={loadList} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}{t("cm.pages_Academy.tekrar_dene")}</Button>
      </Card>;
  };
  return <div className="p-4 md:p-6 max-w-5xl mx-auto">
      {view === "list" && <>
          <PageHeader title={t("cm.pages_Academy.syroce_academy")} subtitle="Departmaniniza ozel egitimleri tamamlayin, sinava girin ve sertifika kazanin." actions={isManager || isAuthor ? <div className="flex items-center gap-2">
                {isAuthor && <Button variant="outline" onClick={() => navigate("/app/academy-manage")}>
                    <Settings2 className="w-4 h-4 mr-2" />{t("cm.pages_Academy.akademi_yonetimi")}</Button>}
                {isManager && <Button variant="outline" onClick={() => navigate("/app/academy-report")}>
                    <ClipboardList className="w-4 h-4 mr-2" />{t("cm.pages_Academy.yonetici_raporu")}</Button>}
              </div> : null} />

          {loadError ? renderLoadErrorState() : <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <KpiCard icon={BookOpen} label={t("cm.pages_Academy.atanan_egitim")} value={totalCourses} intent="info" />
            <KpiCard icon={CheckCircle2} label={t("cm.pages_Academy.tamamlanan")} value={passedCourses} intent="success" />
            <KpiCard icon={Award} label={t("cm.pages_Academy.sertifika")} value={certCount} intent="warning" />
          </div>

          {courses.length === 0 ? <Card className="p-8 text-center text-slate-500">{t("cm.pages_Academy.rolunuz_icin_atanmis_egitim_bu")}</Card> : <div className="space-y-3">
              {courses.map(c => {
            const meta = STATUS_META[c.progress?.status] || STATUS_META.not_started;
            return <Card key={c.id} className="p-4 flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <GraduationCap className="w-5 h-5 text-slate-700 flex-shrink-0" />
                        <h3 className="font-semibold text-slate-900">{c.title}</h3>
                        <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                        {c.draft && <StatusBadge intent="warning">{t("cm.pages_Academy.taslak")}</StatusBadge>}
                      </div>
                      <p className="text-sm text-slate-500 mt-1">{c.summary}</p>
                      <div className="text-xs text-slate-400 mt-2">
                        {c.department_label} · {c.lesson_count}{t("cm.pages_Academy.ders")}{c.question_count}{t("cm.pages_Academy.soru")}{c.progress?.best_score ? ` · En iyi puan: ${c.progress.best_score}` : ""}
                      </div>
                    </div>
                    <Button onClick={() => openCourse(c.id)} className="flex-shrink-0">
                      {c.progress?.status === "passed" ? "Incele" : "Egitime Git"}
                    </Button>
                  </Card>;
          })}
            </div>}

          {certificates.length > 0 && <div className="mt-8">
              <h2 className="text-lg font-bold text-slate-900 mb-3">{t("cm.pages_Academy.sertifikalarim")}</h2>
              <div className="space-y-2">
                {certificates.map(cert => <Card key={cert.id} className="p-4 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <Award className="w-5 h-5 text-amber-500 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="font-medium text-slate-900 truncate">{cert.course_title}</div>
                        <div className="text-xs text-slate-400">{t("cm.pages_Academy.puan")}{cert.score}{t("cm.pages_Academy._kod")}{cert.verification_code}
                        </div>
                      </div>
                    </div>
                    <Button variant="outline" onClick={() => downloadCertificate(cert.id, cert.verification_code)}>
                      <Download className="w-4 h-4 mr-2" />{t("cm.pages_Academy.pdf")}</Button>
                  </Card>)}
              </div>
            </div>}
          </>}
        </>}

      {view === "course" && course && <>
          <PageHeader title={course.title} subtitle={course.summary} actions={<Button variant="outline" onClick={backToList}>
                <ArrowLeft className="w-4 h-4 mr-2" />{t("cm.pages_Academy.geri")}</Button>} />
          {course.draft && <div className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">{t("cm.pages_Academy.bu_egitim_taslak_icerik_icerir")}</div>}
          <div className="space-y-4">
            {(course.lessons || []).map(lesson => {
          const done = (course.progress?.completed_lessons || []).includes(lesson.id);
          return <Card key={lesson.id} className="p-4">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-slate-600" />
                      <h3 className="font-semibold text-slate-900">{lesson.title}</h3>
                    </div>
                    {done ? <StatusBadge intent="success">{t("cm.pages_Academy.tamamlandi")}</StatusBadge> : <Button size="sm" variant="outline" onClick={() => completeLesson(lesson.id)}>{t("cm.pages_Academy.okudum")}</Button>}
                  </div>
                  <div className="prose prose-sm max-w-none" dangerouslySetInnerHTML={renderMarkdown(lesson.body_markdown)} />
                </Card>;
        })}
          </div>
          <div className="mt-6 flex items-center justify-between">
            <div className="text-sm text-slate-500">
              {(course.progress?.completed_lessons || []).length} / {course.lesson_count}{t("cm.pages_Academy.ders_tamamlandi_gecme_notu")}{course.pass_threshold}
            </div>
            <Button onClick={startExam} disabled={(course.progress?.completed_lessons || []).length < course.lesson_count}>{t("cm.pages_Academy.sinava_gir")}</Button>
          </div>
        </>}

      {view === "exam" && exam && <>
          <PageHeader title={`Sinav: ${exam.title}`} subtitle={`${exam.question_count} soru · Gecme notu: ${exam.pass_threshold}`} actions={<Button variant="outline" onClick={() => setView("course")}>
                <ArrowLeft className="w-4 h-4 mr-2" />{t("cm.pages_Academy.geri")}</Button>} />
          <div className="space-y-4">
            {(exam.questions || []).map((q, qi) => <Card key={q.id} className="p-4">
                <div className="font-medium text-slate-900 mb-3">{qi + 1}. {q.prompt}</div>
                <div className="space-y-2">
                  {q.options.map((opt, oi) => <label key={oi} className={`flex items-center gap-2 px-3 py-2 rounded border cursor-pointer ${answers[q.id] === oi ? "border-slate-900 bg-slate-50" : "border-slate-200"}`}>
                      <input type="radio" name={q.id} checked={answers[q.id] === oi} onChange={() => setAnswers(a => ({
                ...a,
                [q.id]: oi
              }))} />
                      <span className="text-sm text-slate-800">{opt}</span>
                    </label>)}
                </div>
              </Card>)}
          </div>
          <div className="mt-6 flex justify-end">
            <Button onClick={submitExam} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}{t("cm.pages_Academy.sinavi_gonder")}</Button>
          </div>
        </>}

      {view === "result" && result && <div className="max-w-xl mx-auto text-center py-8">
          <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-4 ${result.result?.passed ? "bg-emerald-100" : "bg-rose-100"}`}>
            {result.result?.passed ? <CheckCircle2 className="w-9 h-9 text-emerald-600" /> : <ClipboardList className="w-9 h-9 text-rose-600" />}
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mb-2">
            {result.result?.passed ? "Tebrikler, gectiniz!" : "Maalesef gecemediniz"}
          </h2>
          <p className="text-slate-600 mb-1">{t("cm.pages_Academy.puaniniz")}<strong>{result.result?.score}</strong> / 100
            ({result.result?.correct}/{result.result?.total}{t("cm.pages_Academy.dogru")}</p>
          <p className="text-sm text-slate-400 mb-6">{t("cm.pages_Academy.gecme_notu")}{result.result?.pass_threshold}</p>

          {result.certificate && <Card className="p-4 mb-6 text-left flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Award className="w-6 h-6 text-amber-500" />
                <div>
                  <div className="font-medium text-slate-900">{t("cm.pages_Academy.sertifikaniz_hazir")}</div>
                  <div className="text-xs text-slate-400">{t("cm.pages_Academy.kod")}{result.certificate.verification_code}</div>
                </div>
              </div>
              <Button variant="outline" onClick={() => downloadCertificate(result.certificate.id, result.certificate.verification_code)}>
                <Download className="w-4 h-4 mr-2" />{t("cm.pages_Academy.pdf_indir")}</Button>
            </Card>}

          <div className="flex justify-center gap-2">
            <Button variant="outline" onClick={() => course && startExam()}>{t("cm.pages_Academy.tekrar_dene")}</Button>
            <Button onClick={backToList}>{t("cm.pages_Academy.akademiye_don")}</Button>
          </div>
        </div>}
    </div>;
}