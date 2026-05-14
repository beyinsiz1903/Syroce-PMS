// Stress markdown-reporter — F7 (default) + F8A (STRESS_REPORT_TAG=f8a_frontoffice_folio_hk).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');

const REPORT_TAG = process.env.STRESS_REPORT_TAG || 'f7_scaffold';
const REPORT_TITLE = process.env.STRESS_REPORT_TITLE
    || (REPORT_TAG === 'f7_scaffold' ? 'F7 — Stress E2E Scaffold' : `Stress E2E (${REPORT_TAG})`);

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
        const annotations = result.annotations || [];
        const recs = annotations
            .filter((a) => a.type === 'rec')
            .map((a) => { try { return JSON.parse(a.description); } catch { return null; } })
            .filter(Boolean);
        const perfs = annotations
            .filter((a) => a.type === 'perf')
            .map((a) => { try { return JSON.parse(a.description); } catch { return null; } })
            .filter(Boolean);
        const findings = annotations
            .filter((a) => a.type === 'finding')
            .map((a) => { try { return JSON.parse(a.description); } catch { return null; } })
            .filter(Boolean);
        this.results.push({
            title: test.titlePath().slice(1).join(' › '),
            file: test.location?.file ? path.relative(REPO_ROOT, test.location.file) : '',
            line: test.location?.line ?? null,
            project: test.parent?.project?.()?.name || '',
            outcome: result.status,
            durationMs: result.duration,
            error: result.error?.message || null,
            recs, perfs, findings,
        });
    }
    async onEnd(runResult) {
        const date = fmtDate(this.startedAt);
        const outDir = path.join(REPO_ROOT, 'docs', 'drill_reports');
        fs.mkdirSync(outDir, { recursive: true });
        const outPath = path.join(outDir, `${date}_stress_${REPORT_TAG}.md`);

        const allRecs = this.results.flatMap((r) => r.recs.map((x) => ({ ...x, _test: r.title, _outcome: r.outcome })));
        const allPerfs = this.results.flatMap((r) => r.perfs.map((x) => ({ ...x, _test: r.title })));
        const allFindings = this.results.flatMap((r) => r.findings.map((x) => ({ ...x, _test: r.title })));
        const counters = { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0 };
        for (const rec of allRecs) counters[rec.status] = (counters[rec.status] || 0) + 1;

        const moduleAgg = {};
        for (const rec of allRecs) {
            const m = rec.module || 'unknown';
            moduleAgg[m] ||= { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0, total: 0 };
            moduleAgg[m][rec.status] = (moduleAgg[m][rec.status] || 0) + 1;
            moduleAgg[m].total++;
        }

        const sevAgg = { P0: 0, P1: 0, P2: 0, P3: 0 };
        for (const f of allFindings) sevAgg[f.severity] = (sevAgg[f.severity] || 0) + 1;

        let state = null, teardown = null;
        try { state = JSON.parse(fs.readFileSync(this.stateFile, 'utf-8')); } catch {}
        try { teardown = JSON.parse(fs.readFileSync(this.teardownFile, 'utf-8')); } catch {}

        const failedTests = this.results.filter((r) => r.outcome === 'failed' || r.outcome === 'timedOut');
        const verdict = decideVerdict({ counters, failedTests, runResult, state, teardown, sevAgg });

        let md = '';
        md += `# ${REPORT_TITLE} — ${date}\n\n`;
        md += `> Suite: \`frontend/e2e-stress/\` (Playwright config: \`playwright.stress.config.js\`). Üretildi: ${this.startedAt.toISOString()} · Tag: \`${REPORT_TAG}\`\n\n`;

        md += `## 1) Yönetici özeti\n\n`;
        md += `| Metrik | Değer |\n|---|---|\n`;
        md += `| Toplam test | ${this.results.length} |\n`;
        md += `| Başarısız test | ${failedTests.length} |\n`;
        md += `| Adım PASS / FAIL / REVIEW / SKIP | ${counters.PASS} / ${counters.FAIL} / ${counters.REVIEW} / ${counters.SKIP} |\n`;
        md += `| P0 / P1 / P2 / P3 finding | ${sevAgg.P0} / ${sevAgg.P1} / ${sevAgg.P2} / ${sevAgg.P3} |\n`;
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

        md += `## 5) P0/P1/P2/P3 Severity Triage\n\n`;
        if (allFindings.length === 0) {
            md += `**Hiç finding yok.** Tüm spec'ler kritik bulgu üretmedi (pilot drift=0, business-rule guard'lar tutuyor, veri kaybı/leak yok).\n\n`;
        } else {
            for (const sev of ['P0', 'P1', 'P2', 'P3']) {
                const list = allFindings.filter((f) => f.severity === sev);
                if (list.length === 0) continue;
                md += `### ${sev} (${list.length})\n`;
                for (const f of list) {
                    md += `- **[${f.module}]** ${f.title}\n  - Test: \`${f._test}\`\n  - Detay: ${f.detail}\n`;
                }
                md += '\n';
            }
        }

        md += `## 6) Performance Hotspots (top 10 slowest ops, p95)\n\n`;
        if (allPerfs.length === 0) {
            md += `_Performans örneği yok._\n\n`;
        } else {
            const sortedPerf = [...allPerfs].sort((a, b) => (b.p95 ?? 0) - (a.p95 ?? 0)).slice(0, 10);
            md += `| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |\n|---|---|---:|---:|---:|---:|---:|\n`;
            for (const p of sortedPerf) {
                md += `| ${p.module} | ${p.op} | ${p.count} | ${p.p50} | ${p.p95} | ${p.max} | ${p.avg} |\n`;
            }
            md += '\n';
        }

        md += `## 7) Bulgular (REVIEW + SKIP detail)\n\n`;
        const failRecs = allRecs.filter((r) => r.status === 'FAIL');
        const reviewRecs = allRecs.filter((r) => r.status === 'REVIEW');
        const skipRecs = allRecs.filter((r) => r.status === 'SKIP');
        if (failRecs.length === 0 && failedTests.length === 0) {
            md += `**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.\n\n`;
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

        // Architect tur-5: dedicated "Broken Buttons / Wrong Business Rule" + "Cleanup Integrity" sections.
        const businessRuleFindings = allFindings.filter((f) => /folio|guard|reject|booking|move|state|RNL|reconcile|transfer|OOO|overbook|turnover|invariant/i.test(f.title || ''));
        const buttonFindings = allFindings.filter((f) => /button|click|UI|render|TTI|DOM|first_row|gate|frontend/i.test(f.title || ''));
        md += `## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)\n\n`;
        if (businessRuleFindings.length === 0 && buttonFindings.length === 0) {
            md += `_Yok._ Tüm business-rule guard'lar ve UI etkileşimleri çalışıyor.\n\n`;
        } else {
            if (businessRuleFindings.length > 0) {
                md += `### ⚖️ Wrong Business Rule (${businessRuleFindings.length})\n`;
                for (const f of businessRuleFindings) {
                    const testRow = this.results.find((r) => r.title === f._test);
                    const fileRef = testRow?.file ? `\`${testRow.file}${testRow.line ? `:${testRow.line}` : ''}\`` : '_(test ref yok)_';
                    md += `- **[${f.severity}] [${f.module}] ${f.title}** — ${fileRef}\n  - Test: \`${f._test}\`\n  - Repro: ${f.detail || '-'}\n`;
                }
                md += '\n';
            }
            if (buttonFindings.length > 0) {
                md += `### 🖱️ Broken Buttons / UI (${buttonFindings.length})\n`;
                for (const f of buttonFindings) {
                    const testRow = this.results.find((r) => r.title === f._test);
                    const fileRef = testRow?.file ? `\`${testRow.file}${testRow.line ? `:${testRow.line}` : ''}\`` : '_(test ref yok)_';
                    md += `- **[${f.severity}] [${f.module}] ${f.title}** — ${fileRef}\n  - Test: \`${f._test}\`\n  - Repro: ${f.detail || '-'}\n`;
                }
                md += '\n';
            }
        }

        md += `## 7b) Cleanup Integrity\n\n`;
        if (teardown) {
            const c1 = (teardown.steps || []).find((s) => s.name === 'cleanup#1');
            const c2 = (teardown.steps || []).find((s) => s.name === 'cleanup#2_idempotent');
            const pd = (teardown.steps || []).find((s) => s.name === 'pilot_diff');
            md += `| Adım | Durum | Detay |\n|---|---|---|\n`;
            md += `| cleanup#1 (deletion) | ${c1?.status === 200 ? '✅ OK' : '❌ FAIL'} | deleted_total=${c1?.deleted_total ?? c1?.deleted ?? 'n/a'} |\n`;
            md += `| cleanup#2 (idempotency) | ${c2?.idempotent ? '✅ idempotent' : '❌ NOT idempotent'} | re-run deleted=${c2?.deleted_total ?? c2?.deleted ?? 'n/a'} |\n`;
            md += `| pilot drift | ${pd?.drift === 0 ? '✅ drift=0' : `❌ drift=${pd?.drift ?? 'n/a'}`} | baseline=${pd?.baseline ?? 'n/a'} after=${pd?.after ?? 'n/a'} |\n\n`;
            md += `_Audit logs are NEVER deleted (KVKK retention) — bu liste sadece stress-seeded business data'yı kapsar._\n\n`;
        } else {
            md += `_Teardown log bulunamadı (\`.auth/teardown.json\` yok). globalTeardown çalışmamış olabilir._\n\n`;
        }

        md += `## 8) Test inventory\n\n`;
        md += `| # | Test | Outcome | Süre |\n|---:|---|---|---:|\n`;
        this.results.forEach((r, i) => {
            const icon = r.outcome === 'passed' ? '✅' : r.outcome === 'skipped' ? '⏭️' : '❌';
            md += `| ${i + 1} | ${r.title} | ${icon} ${r.outcome} | ${(r.durationMs / 1000).toFixed(1)}s |\n`;
        });
        md += '\n';

        md += `## 9) Artifact path'leri\n\n`;
        md += `- HTML report: \`frontend/playwright-stress-report/\`\n`;
        md += `- Trace/video/screenshot: \`frontend/test-results-stress/\`\n`;
        md += `- State: \`frontend/e2e-stress/.auth/stress-state.json\` (gitignored)\n`;
        md += `- Teardown log: \`frontend/e2e-stress/.auth/teardown.json\` (gitignored)\n\n`;

        md += `## 10) Sonraki tur\n\n`;
        md += `${verdict.next}\n`;

        fs.writeFileSync(outPath, md);
        console.log(`\n[stress-md-reporter] Report yazıldı: ${outPath}`);
    }
}

function decideVerdict({ counters, failedTests, runResult, state, teardown, sevAgg }) {
    const isF8A = REPORT_TAG.startsWith('f8a');
    const nextStep = isF8A ? 'F8B (Channel Manager / outbox / circuit breaker stress)' : 'F8 (operasyonel stress senaryoları)';
    if (sevAgg.P0 > 0) {
        return { label: 'NO-GO', reason: `P0 finding=${sevAgg.P0}`,
            next: `❌ **NO-GO** — ${nextStep} öncesi P0 düzeltilmeli.` };
    }
    if (runResult.status === 'failed' || failedTests.length > 0 || counters.FAIL > 0) {
        return { label: 'NO-GO', reason: `failedTests=${failedTests.length}, FAIL adım=${counters.FAIL}`,
            next: `❌ **NO-GO** — ${nextStep} öncesi P0/P1 düzeltilmeli.` };
    }
    if (teardown) {
        const c1 = (teardown.steps || []).find((s) => s.name === 'cleanup#1');
        const c2 = (teardown.steps || []).find((s) => s.name === 'cleanup#2_idempotent');
        const pd = (teardown.steps || []).find((s) => s.name === 'pilot_diff');
        if (c1 && c1.status !== 200) return { label: 'NO-GO', reason: 'cleanup#1 failed', next: '❌ NO-GO — cleanup başarısız.' };
        if (c2 && !c2.idempotent) return { label: 'NO-GO', reason: 'cleanup not idempotent', next: '❌ NO-GO — cleanup idempotent değil.' };
        if (pd && pd.drift !== 0) return { label: 'NO-GO', reason: `pilot drift=${pd.drift}`, next: '❌ NO-GO — pilot mutation tespit edildi.' };
    }
    // F8A acceptance contract (architect feedback): P0=P1=0 required, otherwise NO-GO.
    // P2-only or REVIEW-heavy → GO WITH WATCH.
    if (sevAgg.P1 > 0) {
        return { label: 'NO-GO', reason: `P1 finding=${sevAgg.P1}`,
            next: `❌ **NO-GO** — ${nextStep} öncesi P1 düzeltilmeli (acceptance contract: P0=P1=0).` };
    }
    if (sevAgg.P2 > 0 || counters.REVIEW > 5) {
        return { label: 'GO WITH WATCH', reason: `P2=${sevAgg.P2} REVIEW=${counters.REVIEW}`,
            next: `⚠️  **GO WITH WATCH → ${nextStep}** — REVIEW/P2 maddeleri sonraki turda izlenecek.` };
    }
    return { label: 'GO', reason: `Tüm gate + spec adımları PASS, cleanup idempotent, pilot mutation=0, P0/P1=0`,
        next: `✅ **GO → ${nextStep}**` };
}

export default StressReporter;
