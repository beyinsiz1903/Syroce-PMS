// F7 stress markdown-reporter — docs/drill_reports/YYYYMMDD_stress_f7_scaffold.md
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

class StressReporter {
    constructor() {
        this.results = [];
        this.startedAt = new Date();
        this.stateFile = path.join(__dirname, '.auth', 'stress-state.json');
        this.teardownFile = path.join(__dirname, '.auth', 'teardown.json');
    }
    onTestEnd(test, result) {
        const recs = (result.annotations || [])
            .filter((a) => a.type === 'rec')
            .map((a) => { try { return JSON.parse(a.description); } catch { return null; } })
            .filter(Boolean);
        this.results.push({
            title: test.titlePath().slice(1).join(' › '),
            file: test.location?.file ? path.relative(REPO_ROOT, test.location.file) : '',
            project: test.parent?.project?.()?.name || '',
            outcome: result.status,
            durationMs: result.duration,
            error: result.error?.message || null,
            recs,
        });
    }
    async onEnd(runResult) {
        const date = fmtDate(this.startedAt);
        const outDir = path.join(REPO_ROOT, 'docs', 'drill_reports');
        fs.mkdirSync(outDir, { recursive: true });
        const outPath = path.join(outDir, `${date}_stress_f7_scaffold.md`);

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

        let state = null, teardown = null;
        try { state = JSON.parse(fs.readFileSync(this.stateFile, 'utf-8')); } catch {}
        try { teardown = JSON.parse(fs.readFileSync(this.teardownFile, 'utf-8')); } catch {}

        const failedTests = this.results.filter((r) => r.outcome === 'failed' || r.outcome === 'timedOut');
        const verdict = decideVerdict({ counters, failedTests, runResult, state, teardown });

        let md = '';
        md += `# F7 — Stress E2E Scaffold — ${date}\n\n`;
        md += `> Suite: \`frontend/e2e-stress/\` (Playwright config: \`playwright.stress.config.js\`). Üretildi: ${this.startedAt.toISOString()}\n\n`;

        md += `## 1) Yönetici özeti\n\n`;
        md += `| Metrik | Değer |\n|---|---|\n`;
        md += `| Toplam test | ${this.results.length} |\n`;
        md += `| Başarısız test | ${failedTests.length} |\n`;
        md += `| Adım PASS / FAIL / REVIEW / SKIP | ${counters.PASS} / ${counters.FAIL} / ${counters.REVIEW} / ${counters.SKIP} |\n`;
        md += `| Süre | ${(runResult.duration / 1000).toFixed(1)}s |\n`;
        md += `| Final verdict | **${verdict.label}** — ${verdict.reason} |\n\n`;

        if (state) {
            const c = state.seed_response?.seeded_counts || {};
            const tm = state.seed_response?.timing_ms || {};
            md += `## 2) Seed snapshot (globalSetup)\n\n`;
            md += `- prefix: \`${state.data_prefix}\`\n`;
            md += `- room_count: \`${state.room_count}\`\n`;
            md += `- counts: rooms=${c.rooms} guests=${c.guests} bookings=${c.bookings} folios=${c.folios} charges=${c.folio_charges} rnl=${c.room_night_locks} hk=${c.housekeeping_tasks}\n`;
            md += `- timing_ms: factory=${tm.factory} insert=${tm.insert} total=${tm.total}\n`;
            md += `- external_calls_made: \`${JSON.stringify(state.seed_response?.external_calls_made)}\`\n`;
            md += `- tenant_context_used: \`${state.seed_response?.tenant_context_used}\`\n`;
            md += `- gates: \`${JSON.stringify(state.seed_response?.gates)}\`\n\n`;
        }

        if (teardown) {
            md += `## 3) Cleanup snapshot (globalTeardown)\n\n`;
            for (const s of teardown.steps || []) {
                if (s.name?.startsWith('cleanup')) {
                    const dc = s.body?.deleted_counts || {};
                    const total = Object.values(dc).reduce((a, b) => a + b, 0);
                    md += `- **${s.name}**: status=${s.status} deleted_total=${total} ms=${s.body?.timing_ms?.cleanup}${s.idempotent !== undefined ? ` idempotent=${s.idempotent}` : ''}\n`;
                }
            }
            const pd = (teardown.steps || []).find((s) => s.name === 'pilot_diff');
            if (pd) {
                md += `- **pilot_diff**: baseline_bookings=${pd.baseline?.bookings} after_bookings=${pd.after?.bookings} drift=${pd.drift}\n`;
            }
            md += '\n';
        }

        md += `## 4) Modül bazlı tablo\n\n`;
        md += `| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |\n|---|---:|---:|---:|---:|---:|\n`;
        const sorted = Object.entries(moduleAgg).sort(([a], [b]) => a.localeCompare(b));
        for (const [m, c] of sorted) {
            md += `| ${m} | ${c.PASS} | ${c.FAIL} | ${c.REVIEW} | ${c.SKIP} | ${c.total} |\n`;
        }
        md += '\n';

        md += `## 5) Bulgular\n\n`;
        const failRecs = allRecs.filter((r) => r.status === 'FAIL');
        const reviewRecs = allRecs.filter((r) => r.status === 'REVIEW');
        const skipRecs = allRecs.filter((r) => r.status === 'SKIP');
        if (failRecs.length === 0 && failedTests.length === 0) {
            md += `**P0/P1: yok.** Tüm testler ve adımlar PASS / REVIEW / SKIP olarak işaretli.\n\n`;
        } else {
            for (const r of failRecs) {
                md += `### ❌ FAIL [${r.module}] ${r.step}\n- Test: \`${r._test}\`\n- Endpoint: \`${r.endpoint || '-'}\` HTTP=\`${r.http ?? '-'}\`\n- Not: ${r.note || '-'}\n\n`;
            }
            for (const t of failedTests) {
                md += `### ❌ Test failure — ${t.title}\n- File: \`${t.file}\`  Süre: ${(t.durationMs / 1000).toFixed(1)}s\n- Hata: ${(t.error || '').split('\n').slice(0, 4).join('  ')}\n\n`;
            }
        }
        if (reviewRecs.length) {
            md += `### REVIEW (${reviewRecs.length})\n`;
            for (const r of reviewRecs) md += `- **[${r.module}]** ${r.step} — ${r.note || '-'}\n`;
            md += '\n';
        }
        if (skipRecs.length) {
            md += `### SKIP (${skipRecs.length})\n`;
            for (const r of skipRecs) md += `- **[${r.module}]** ${r.step} — ${r.note || '-'}\n`;
            md += '\n';
        }

        md += `## 6) Test inventory\n\n`;
        md += `| # | Test | Outcome | Süre |\n|---:|---|---|---:|\n`;
        this.results.forEach((r, i) => {
            const icon = r.outcome === 'passed' ? '✅' : r.outcome === 'skipped' ? '⏭️' : '❌';
            md += `| ${i + 1} | ${r.title} | ${icon} ${r.outcome} | ${(r.durationMs / 1000).toFixed(1)}s |\n`;
        });
        md += '\n';

        md += `## 7) Artifact path'leri\n\n`;
        md += `- HTML report: \`frontend/playwright-stress-report/\`\n`;
        md += `- Trace/video/screenshot: \`frontend/test-results-stress/\`\n`;
        md += `- State: \`frontend/e2e-stress/.auth/stress-state.json\` (gitignored)\n`;
        md += `- Teardown log: \`frontend/e2e-stress/.auth/teardown.json\` (gitignored)\n\n`;

        md += `## 8) F8'e geçilebilir mi?\n\n`;
        md += `${verdict.f8}\n`;

        fs.writeFileSync(outPath, md);
        console.log(`\n[stress-md-reporter] Report yazıldı: ${outPath}`);
    }
}

function decideVerdict({ counters, failedTests, runResult, state, teardown }) {
    if (runResult.status === 'failed' || failedTests.length > 0 || counters.FAIL > 0) {
        return { label: 'NO-GO', reason: `failedTests=${failedTests.length}, FAIL adım=${counters.FAIL}`,
            f8: '❌ **NO-GO** — F8 öncesi P0/P1 düzeltilmeli.' };
    }
    // Cleanup başarısız ise P1
    if (teardown) {
        const c1 = (teardown.steps || []).find((s) => s.name === 'cleanup#1');
        const c2 = (teardown.steps || []).find((s) => s.name === 'cleanup#2_idempotent');
        const pd = (teardown.steps || []).find((s) => s.name === 'pilot_diff');
        if (c1 && c1.status !== 200) return { label: 'NO-GO', reason: 'cleanup#1 failed', f8: '❌ NO-GO — cleanup başarısız.' };
        if (c2 && !c2.idempotent) return { label: 'NO-GO', reason: 'cleanup not idempotent', f8: '❌ NO-GO — cleanup idempotent değil.' };
        if (pd && pd.drift !== 0) return { label: 'NO-GO', reason: `pilot drift=${pd.drift}`, f8: '❌ NO-GO — pilot mutation tespit edildi.' };
    }
    if (counters.REVIEW > 5) {
        return { label: 'GO WITH WATCH', reason: `REVIEW=${counters.REVIEW}`,
            f8: '⚠️  **GO WITH WATCH** — F8\'e geçilebilir, REVIEW adımları F8 boyunca takip edilmeli.' };
    }
    return { label: 'GO', reason: `Tüm gate + bulk-seed adımları PASS, cleanup idempotent, pilot mutation=0`,
        f8: '✅ **GO → F8** — Stress E2E motoru senaryolar için hazır.' };
}

export default StressReporter;
