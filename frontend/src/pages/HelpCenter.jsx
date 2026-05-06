import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import {
  BookOpen, ChevronRight, FileText, Hotel, LifeBuoy, Loader2,
  Package, Rocket, ScrollText, Search, Tag,
} from "lucide-react";

const ICON_MAP = {
  Rocket, Hotel, DollarSign: BookOpen, Package, ScrollText,
  BookOpen, FileText,
};

// Minimal Markdown renderer — no external dep. Supports:
// # ## ### headings, **bold**, *italic*, `code`, ``` blocks, lists,
// links, paragraphs, horizontal rules, tables.
function renderMarkdown(src) {
  if (!src) return null;
  const escape = (s) => s
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  // v41 Bug BF: full attribute-context escape — must encode quotes too,
  // otherwise safeUrl-allowed prefix with embedded `"` enables attribute
  // injection (e.g. `https://ok.com" onmouseover="alert(1)`).
  const escapeAttr = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  // v41 Bug BF: allowlist only http(s)/mailto/tel/relative URLs; reject
  // protocol-relative `//...` to prevent scheme inheritance via base href.
  const safeUrl = (u) => {
    const t = String(u || "").trim();
    if (!t) return "#";
    if (/^\/\//.test(t)) return "#"; // reject protocol-relative
    if (/^(\/|#|\?)/.test(t)) return t;
    if (/^(https?:|mailto:|tel:)/i.test(t)) return t;
    return "#";
  };
  const inline = (s) => escape(s)
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-gray-100 rounded text-xs font-mono">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(#\/help\/([a-z0-9-]+)\)/g,
             '<a class="text-blue-600 hover:underline" data-slug="$2" href="#">$1</a>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,
             (_m, txt, url) => `<a class="text-blue-600 hover:underline" target="_blank" rel="noopener" href="${escapeAttr(safeUrl(url))}">${txt}</a>`);

  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (/^```/.test(ln)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;
      out.push(`<pre class="bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-auto my-3"><code>${escape(buf.join("\n"))}</code></pre>`);
      continue;
    }
    let m;
    if ((m = ln.match(/^###\s+(.*)$/))) { out.push(`<h3 class="text-base font-semibold mt-5 mb-2">${inline(m[1])}</h3>`); i++; continue; }
    if ((m = ln.match(/^##\s+(.*)$/))) { out.push(`<h2 class="text-lg font-bold mt-6 mb-2">${inline(m[1])}</h2>`); i++; continue; }
    if ((m = ln.match(/^#\s+(.*)$/))) { out.push(`<h1 class="text-2xl font-bold mt-2 mb-3">${inline(m[1])}</h1>`); i++; continue; }
    if (/^---+\s*$/.test(ln)) { out.push('<hr class="my-4 border-gray-200" />'); i++; continue; }
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
      while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i++; }
      const html = rows.map((r, idx) => {
        if (/^\|[\s:-]+\|/.test(r)) return "";
        const cells = r.split("|").slice(1, -1)
          .map((c) => `<td class="border px-3 py-1.5 text-sm">${inline(c.trim())}</td>`)
          .join("");
        const tag = idx === 0 ? "th" : "td";
        const replaced = cells.replace(/<td/g, `<${tag}`).replace(/<\/td>/g, `</${tag}>`);
        return `<tr>${replaced}</tr>`;
      }).join("");
      out.push(`<table class="border-collapse border my-3"><tbody>${html}</tbody></table>`);
      continue;
    }
    if (ln.trim() === "") { i++; continue; }
    // paragraph (collect contiguous non-empty lines)
    const buf = [];
    while (i < lines.length && lines[i].trim() !== ""
           && !/^[#`|]|^\s*[-*\d]\s+|^---+/.test(lines[i])) {
      buf.push(lines[i]); i++;
    }
    out.push(`<p class="my-2 leading-relaxed text-sm text-gray-800">${inline(buf.join(" "))}</p>`);
  }
  return { __html: out.join("\n") };
}

export default function HelpCenter({ user, tenant, onLogout }) {
  const [index, setIndex] = useState(null);
  const [activeSlug, setActiveSlug] = useState(null);
  const [article, setArticle] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    axios.get("/help/index").then((r) => {
      setIndex(r.data);
      const first = r.data?.categories?.[0]?.articles?.[0]?.slug;
      if (first) setActiveSlug(first);
    }).catch(() => toast.error("İçerik dizini yüklenemedi"));
  }, []);

  useEffect(() => {
    if (!activeSlug) return;
    setLoading(true);
    axios.get(`/help/articles/${activeSlug}`)
      .then((r) => setArticle(r.data))
      .catch(() => toast.error("Makale yüklenemedi"))
      .finally(() => setLoading(false));
  }, [activeSlug]);

  const search = async () => {
    if (!query || query.trim().length < 2) { setResults(null); return; }
    try {
      const { data } = await axios.get("/help/search", { params: { q: query } });
      setResults(data);
    } catch { toast.error("Arama başarısız"); }
  };

  const handleBodyClick = (e) => {
    const a = e.target.closest("a[data-slug]");
    if (a) {
      e.preventDefault();
      setActiveSlug(a.getAttribute("data-slug"));
      setResults(null);
    }
  };

  const html = useMemo(() => renderMarkdown(article?.body_markdown), [article]);

  return (
    <>
    <div className="p-4 lg:p-6 space-y-4">
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2 w-full max-w-md">
          <div className="relative flex-1">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              className="w-full border rounded pl-9 pr-3 py-2 text-sm"
              placeholder="Yardım ara (en az 2 harf)…"
            />
          </div>
          <button onClick={search} className="px-3 py-2 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700">Ara</button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <aside className="col-span-12 md:col-span-3 bg-white border rounded-lg p-3 max-h-[80vh] overflow-auto">
          {!index ? (
            <div className="text-gray-500 text-sm flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…
            </div>
          ) : (
            index.categories.map((cat) => {
              const Icon = ICON_MAP[cat.icon] || BookOpen;
              return (
                <div key={cat.key} className="mb-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase mb-1">
                    <Icon className="h-3.5 w-3.5" /> {cat.title}
                  </div>
                  <ul className="space-y-1">
                    {cat.articles.map((a) => (
                      <li key={a.slug}>
                        <button
                          onClick={() => { setActiveSlug(a.slug); setResults(null); }}
                          className={`flex items-center gap-1 w-full text-left px-2 py-1 rounded text-sm hover:bg-indigo-50 ${
                            activeSlug === a.slug ? "bg-indigo-100 text-indigo-800 font-medium" : "text-gray-700"
                          }`}>
                          <ChevronRight className="h-3 w-3 opacity-50" /> {a.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })
          )}
        </aside>

        <main className="col-span-12 md:col-span-9 bg-white border rounded-lg p-6 min-h-[70vh]">
          {results ? (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold">"{results.query}" için {results.count} sonuç</h2>
                <button onClick={() => setResults(null)} className="text-sm text-blue-600 hover:underline">Aramayı kapat</button>
              </div>
              {results.items.length === 0 ? (
                <p className="text-gray-500 text-sm">Sonuç bulunamadı.</p>
              ) : (
                <ul className="space-y-3">
                  {results.items.map((r) => (
                    <li key={r.slug} className="border rounded p-3 hover:bg-gray-50">
                      <button onClick={() => { setActiveSlug(r.slug); setResults(null); }}
                              className="text-left w-full">
                        <div className="font-semibold text-indigo-700">{r.title}</div>
                        <div className="text-xs text-gray-500 mt-0.5">{r.category_title}</div>
                        {r.snippet && <div className="text-sm text-gray-600 mt-2">{r.snippet}</div>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : loading ? (
            <div className="flex items-center gap-2 text-gray-500"><Loader2 className="h-5 w-5 animate-spin" /> Yükleniyor…</div>
          ) : article ? (
            <article onClick={handleBodyClick} className="prose-sm max-w-none">
              <div className="text-xs text-gray-500 mb-2 flex items-center gap-2">
                <BookOpen className="h-3 w-3" /> {article.category_title}
                {(article.tags || []).map((t) => (
                  <span key={t} className="ml-1 inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded-full">
                    <Tag className="h-3 w-3" /> {t}
                  </span>
                ))}
              </div>
              <div dangerouslySetInnerHTML={html} />
            </article>
          ) : (
            <p className="text-gray-500 text-sm">Soldan bir makale seçin.</p>
          )}
        </main>
      </div>
    </div>
    </>
  );
}
