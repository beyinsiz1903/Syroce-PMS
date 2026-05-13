import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');

function fmtDate(d = new Date()) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}${m}${dd}`;
}

class BusinessReporter {
    constructor() {
        this.results = [];
        this.startedAt = new Date();
        this.dataRegistry = path.join(__dirname, '.auth', 'data-registry.json');
    }
    onTestEnd(test, result) {
        const recs = (result.annotations || [])
            .filter((a) => a.type === 'rec')
            .map((a) => { try { return JSON.parse(a.description); } catch { return null; } })
            .filter(Boolean);
        const attachments = (result.attachments || []).map((a) => ({ name: a.name, path: a.path, contentType: a.contentType }));
        this.results.push({
            title: test.titlePath().slice(1).join(' › '),
            file: test.location?.file ? path.relative(REPO_ROOT, test.location.file) : '',
            project: test.parent?.project?.()?.name || '',
            outcome: result.status, // passed|failed|skipped|timedOut|interrupted
            durationMs: result.duration,
            error: result.error?.message || null,
            recs,
            attachments,
        });
    }
    async onEnd(runResult) {
        const date = fmtDate(this.startedAt);
        const outDir = path.join(REPO_ROOT, 'docs', 'drill_reports');
        fs.mkdirSync(outDir, { recursive: true });
        const outPath = path.join(outDir, `${date}_full_ui_business_e2e.md`);

        const allRecs = this.results.flatMap((r) => r.recs.map((x) => ({ ...x, _test: r.title, _outcome: r.outcome })));
        const counters = { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0 };
        for (const rec of allRecs) counters[rec.status] = (counters[rec.status] || 0) + 1;

        const moduleAgg = {};
        for (const rec of allRecs) {
            const m = rec.module || 'unknown';
            moduleAgg[m] ||= { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0, total: 0 };
            moduleAgg[m][rec.status] = (moduleAgg[m][rec.status] || 0) + 1;
            moduleAgg[m].total++;
        }

        const failedTests = this.results.filter((r) => r.outcome === 'failed' || r.outcome === 'timedOut');
        const reviewSteps = allRecs.filter((r) => r.status === 'REVIEW');
        const skipSteps = allRecs.filter((r) => r.status === 'SKIP');

        let dataEntities = [];
        try { dataEntities = JSON.parse(fs.readFileSync(this.dataRegistry, 'utf-8')).entities || []; } catch {}

        const verdict = decideVerdict({ counters, failedTests, runResult });

        let md = '';
        md += `# Full UI + Business E2E — ${date}\n\n`;
        md += `> Suite: \`frontend/e2e-business/\` (Playwright). Üretildi: ${this.startedAt.toISOString()}\n\n`;
        md += `## 1. Yönetici özeti\n\n`;
        md += `- Toplam test: **${this.results.length}**\n`;
        md += `- Başarısız test: **${failedTests.length}**\n`;
        md += `- Adım sayaçları: PASS=${counters.PASS} | FAIL=${counters.FAIL} | REVIEW=${counters.REVIEW} | SKIP=${counters.SKIP}\n`;
        md += `- Süre: ${(runResult.duration / 1000).toFixed(1)}s\n`;
        md += `- Son karar: **${verdict.label}** — ${verdict.reason}\n\n`;

        md += `## 2. Modül bazlı tablo\n\n`;
        md += `| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |\n|---|---:|---:|---:|---:|---:|\n`;
        const sorted = Object.entries(moduleAgg).sort(([a], [b]) => a.localeCompare(b));
        for (const [m, c] of sorted) {
            md += `| ${m} | ${c.PASS} | ${c.FAIL} | ${c.REVIEW} | ${c.SKIP} | ${c.total} |\n`;
        }
        md += '\n';

        md += `## 3. Kritik bulgular (FAIL adımlar + başarısız testler)\n\n`;
        const failRecs = allRecs.filter((r) => r.status === 'FAIL');
        if (failRecs.length === 0 && failedTests.length === 0) {
            md += `_Yok — tüm testler ve adımlar geçti veya REVIEW/SKIP olarak işaretli._\n\n`;
        } else {
            for (const r of failRecs) {
                md += `### ❌ [${r.module}] ${r.step}\n`;
                md += `- Test: \`${r._test}\`\n- Endpoint: \`${r.endpoint || '-'}\`  HTTP: \`${r.http ?? '-'}\`\n- Not: ${r.note || '-'}\n\n`;
            }
            for (const t of failedTests) {
                md += `### ❌ Test failure — ${t.title}\n`;
                md += `- File: \`${t.file}\`  Project: \`${t.project}\`  Süre: ${(t.durationMs / 1000).toFixed(1)}s\n`;
                md += `- Hata: ${(t.error || '').split('\n').slice(0, 4).join('  ')}\n`;
                if (t.attachments.length) {
                    md += `- Artifacts:\n`;
                    for (const a of t.attachments) {
                        if (!a.path) continue;
                        md += `  - ${a.name}: \`${path.relative(REPO_ROOT, a.path)}\`\n`;
                    }
                }
                md += '\n';
            }
        }

        md += `## 4. Test verileri (oluşturulan / temizlenen)\n\n`;
        if (dataEntities.length === 0) {
            md += `_Hiç entity oluşturulmadı veya kayıt bulunamadı._\n\n`;
        } else {
            md += `| Kind | Label | ID | Cleanup | Endpoint |\n|---|---|---|---|---|\n`;
            for (const e of dataEntities) {
                md += `| ${e.kind} | ${e.label} | ${e.id || '-'} | ${e.cleanup} | ${e.endpoint || '-'} |\n`;
            }
            md += '\n';
        }

        md += `## 5. REVIEW + SKIP adımlar\n\n`;
        if (reviewSteps.length === 0 && skipSteps.length === 0) {
            md += `_Yok._\n\n`;
        } else {
            for (const status of ['REVIEW', 'SKIP']) {
                const arr = status === 'REVIEW' ? reviewSteps : skipSteps;
                if (!arr.length) continue;
                md += `### ${status} (${arr.length})\n`;
                for (const r of arr) {
                    md += `- **[${r.module}]** ${r.step} — ${r.note || '-'} ${r.endpoint ? `(\`${r.endpoint}\` ${r.http ?? ''})` : ''}\n`;
                }
                md += '\n';
            }
        }

        md += `## 6. Risk sınıflandırması (heuristic)\n\n`;
        md += `- **P0 (canlıya çıkışı engeller)**: failedTests=${failedTests.length}, FAIL adım=${counters.FAIL}\n`;
        md += `- **P1 (pilot öncesi düzeltilmeli)**: REVIEW kritik modüllerde — bkz. §5\n`;
        md += `- **P2 (pilot sonrası)**: secondary modül REVIEW/SKIP\n`;
        md += `- **P3 (kozmetik)**: console error allowlist dışı (varsa raporlandı)\n\n`;

        md += `## 7. Artifact path'leri\n\n`;
        md += `- HTML report: \`frontend/playwright-business-report/\`\n`;
        md += `- Trace/video/screenshot: \`frontend/test-results-business/\`\n`;
        md += `- Data registry: \`frontend/e2e-business/.auth/data-registry.json\`\n`;
        md += `- Auth state: \`frontend/e2e-business/.auth/admin.json\` (gitignore önerilir)\n\n`;

        md += `## 8. Test inventory\n\n`;
        md += `| # | Test | Project | Outcome | Süre |\n|---:|---|---|---|---:|\n`;
        this.results.forEach((r, i) => {
            const icon = r.outcome === 'passed' ? '✅' : r.outcome === 'skipped' ? '⏭️' : '❌';
            md += `| ${i + 1} | ${r.title} | ${r.project} | ${icon} ${r.outcome} | ${(r.durationMs / 1000).toFixed(1)}s |\n`;
        });

        fs.writeFileSync(outPath, md);
        console.log(`\n[business-md-reporter] Report yazıldı: ${outPath}`);
    }
}

function decideVerdict({ counters, failedTests, runResult }) {
    if (runResult.status === 'failed' || failedTests.length > 0 || counters.FAIL > 0) {
        return { label: 'NO-GO', reason: `failedTests=${failedTests.length}, FAIL adım=${counters.FAIL}` };
    }
    if (counters.REVIEW > 5) {
        return { label: 'GO WITH WATCH', reason: `REVIEW=${counters.REVIEW} adım — pilot sırasında manuel takip` };
    }
    return { label: 'GO', reason: `Tüm testler PASS, kritik FAIL yok` };
}

export default BusinessReporter;
