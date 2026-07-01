// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke markdown drill-report reporter.
// ─────────────────────────────────────────────────────────────────────────
// Models frontend/e2e-stress/markdown-reporter.mjs, adapted to the mobile
// render-only smoke annotation schema emitted by mobile/e2e/smoke.spec.ts:
//   screen-key · screen-path · screen-crit · http-status · nav-ms ·
//   inspect · console-errors-count · network-errors-count · network-errors ·
//   finding (P0 PII, JSON)
//
// Classification (F10A doctrine, mobile/e2e/README.md):
//   - failed / timedOut          → FAIL  (hard-fail: empty UI, console error, PII)
//   - skipped                    → SKIP
//   - passed + network 4xx/5xx   → REVIEW (module-blocked / route-missing → P2, never PASS)
//   - passed (clean)             → PASS
//
// Severity findings:
//   - PII / token leak in DOM    → P0  (from `finding` annotations)
//   - module-blocked REVIEW      → P2
//
// Verdict gate (mirrors stress doctrine, GO never silently upgraded):
//   - P0 > 0 or failedTests > 0          → NO-GO
//   - P2 / REVIEW > 0                     → GO WITH WATCH
//   - otherwise                           → GO
//
// Output: docs/drill_reports/YYYYMMDD_f10a_mobile_smoke.md
// ─────────────────────────────────────────────────────────────────────────
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// mobile/e2e → repo root is two levels up.
const REPO_ROOT = path.resolve(__dirname, '..', '..');

const REPORT_TAG = process.env.MOBILE_REPORT_TAG || 'f10a_mobile_smoke';
const REPORT_TITLE = process.env.MOBILE_REPORT_TITLE || 'F10A — Mobile Smoke Matrix';

function fmtDate(d = new Date()) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}${m}${dd}`;
}

function annMap(annotations) {
    const map = {};
    for (const a of annotations || []) {
        if (a.type in map) {
            if (!Array.isArray(map[a.type])) map[a.type] = [map[a.type]];
            map[a.type].push(a.description);
        } else {
            map[a.type] = a.description;
        }
    }
    return map;
}

function parseJSON(s, fallback = null) {
    try { return JSON.parse(s); } catch { return fallback; }
}

class MobileSmokeReporter {
    constructor() {
        // Keyed by stable test identity so retry attempts (CI `retries: 1`)
        // collapse to the final attempt — the last onTestEnd for a given
        // test overwrites earlier ones, so a flaky pass-on-retry does not
        // inflate FAIL counts into a false NO-GO.
        this.resultsById = new Map();
        this.startedAt = new Date();
    }

    onTestEnd(test, result) {
        const a = annMap(result.annotations);
        const role = (test.titlePath().slice(1, 2)[0] || '').replace(/^Mobile smoke ·\s*/, '') || 'unknown';

        const networkErrorsRaw = []
            .concat(a['network-errors'] || [])
            .flatMap((s) => parseJSON(s, []) || []);
        const findings = []
            .concat(a['finding'] || [])
            .map((s) => parseJSON(s))
            .filter(Boolean);

        const outcome = result.status; // passed | failed | timedOut | skipped | interrupted
        const isFail = outcome === 'failed' || outcome === 'timedOut' || outcome === 'interrupted';
        const isSkip = outcome === 'skipped';
        const moduleBlocked = !isFail && !isSkip && networkErrorsRaw.length > 0;

        let status;
        if (isFail) status = 'FAIL';
        else if (isSkip) status = 'SKIP';
        else if (moduleBlocked) status = 'REVIEW';
        else status = 'PASS';

        const id = test.id || test.titlePath().slice(1).join(' › ');
        this.resultsById.set(id, {
            title: test.titlePath().slice(1).join(' › '),
            file: test.location?.file ? path.relative(REPO_ROOT, test.location.file) : '',
            line: test.location?.line ?? null,
            role,
            screenKey: a['screen-key'] || null,
            screenPath: a['screen-path'] || null,
            screenCrit: a['screen-crit'] || null,
            httpStatus: a['http-status'] ? Number(a['http-status']) : null,
            navMs: a['nav-ms'] ? Number(a['nav-ms']) : null,
            consoleErrors: a['console-errors-count'] ? Number(a['console-errors-count']) : 0,
            networkErrors: networkErrorsRaw,
            piiFindings: findings,
            outcome,
            status,
            moduleBlocked,
            durationMs: result.duration,
            error: result.error?.message || null,
        });
    }

    async onEnd(runResult) {
        // Materialize one row per logical test (final attempt wins).
        this.results = [...this.resultsById.values()];
        const date = fmtDate(this.startedAt);
        const outDir = path.join(REPO_ROOT, 'docs', 'drill_reports');
        fs.mkdirSync(outDir, { recursive: true });
        const outPath = path.join(outDir, `${date}_${REPORT_TAG}.md`);

        const counters = { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0 };
        for (const r of this.results) counters[r.status] = (counters[r.status] || 0) + 1;

        // Severity aggregation: PII findings = P0; module-blocked REVIEW = P2.
        const sevAgg = { P0: 0, P1: 0, P2: 0, P3: 0 };
        const p0Findings = [];
        const p2Findings = [];
        for (const r of this.results) {
            for (const f of r.piiFindings) {
                sevAgg.P0++;
                p0Findings.push({ ...f, _test: r.title, _screen: r.screenKey });
            }
            if (r.moduleBlocked) {
                sevAgg.P2++;
                p2Findings.push({
                    _test: r.title,
                    screen: r.screenKey,
                    path: r.screenPath,
                    http: r.httpStatus,
                    detail: r.networkErrors
                        .slice(0, 3)
                        .map((n) => `${n.status} ${n.url}`)
                        .join(' · '),
                });
            }
        }

        const failedTests = this.results.filter(
            (r) => r.outcome === 'failed' || r.outcome === 'timedOut' || r.outcome === 'interrupted',
        );

        // Per-role aggregation.
        const roleAgg = {};
        for (const r of this.results) {
            roleAgg[r.role] ||= { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0, total: 0 };
            roleAgg[r.role][r.status] = (roleAgg[r.role][r.status] || 0) + 1;
            roleAgg[r.role].total++;
        }

        // Per-criticality aggregation (P0/P1/P2/P3 screens).
        const critAgg = {};
        for (const r of this.results) {
            const c = r.screenCrit || 'n/a';
            critAgg[c] ||= { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0, total: 0 };
            critAgg[c][r.status] = (critAgg[c][r.status] || 0) + 1;
            critAgg[c].total++;
        }

        const verdict = decideVerdict({ counters, failedTests, runResult, sevAgg });

        let md = '';
        md += `# ${REPORT_TITLE} — ${date}\n\n`;
        md += `> Suite: \`mobile/e2e/\` (Playwright on Expo Web, config: \`mobile/e2e/playwright.config.ts\`). `;
        md += `Üretildi: ${this.startedAt.toISOString()} · Tag: \`${REPORT_TAG}\`\n\n`;
        md += `> **Kapsam notu:** F10A render-only mobile smoke matrix'idir — `;
        md += `/100 mobile kapsamı DEĞİLDİR (F10B–F10G native/derin akış ayrı ve açık). `;
        md += `Merkezi referans: \`docs/TEST_COVERAGE_SCORECARD_100.md\`.\n\n`;

        md += `## 1) Yönetici özeti\n\n`;
        md += `| Metrik | Değer |\n|---|---|\n`;
        md += `| Toplam test | ${this.results.length} |\n`;
        md += `| Başarısız test | ${failedTests.length} |\n`;
        md += `| PASS / FAIL / REVIEW / SKIP | ${counters.PASS} / ${counters.FAIL} / ${counters.REVIEW} / ${counters.SKIP} |\n`;
        md += `| P0 / P1 / P2 / P3 finding | ${sevAgg.P0} / ${sevAgg.P1} / ${sevAgg.P2} / ${sevAgg.P3} |\n`;
        md += `| Süre | ${(runResult.duration / 1000).toFixed(1)}s |\n`;
        md += `| Final verdict | **${verdict.label}** — ${verdict.reason} |\n\n`;

        md += `## 2) Doktrin invariant'ları\n\n`;
        md += `- **Read-only smoke** — POST/PUT/DELETE yok, pilot mutation = 0 (render-only matrix).\n`;
        md += `- **external_calls = []** — OTA / Quick-ID / Expo push gibi gerçek outbound yok.\n`;
        md += `- **PII/token leak** — JWT / PAN / bearer / api-key DOM taraması (P0, hard-fail).\n`;
        md += `- **Module-blocked / route-missing** — REVIEW (P2), asla PASS değil.\n`;
        md += `- **Skip-as-pass yok** — boş ekran, console error ve PII leak spec'i hard-fail eder.\n\n`;

        md += `## 3) Rol bazlı tablo\n\n`;
        md += `| Rol | PASS | FAIL | REVIEW | SKIP | Toplam |\n|---|---:|---:|---:|---:|---:|\n`;
        for (const [role, c] of Object.entries(roleAgg).sort(([a], [b]) => a.localeCompare(b))) {
            md += `| ${role} | ${c.PASS} | ${c.FAIL} | ${c.REVIEW} | ${c.SKIP} | ${c.total} |\n`;
        }
        md += '\n';

        md += `## 4) Kritiklik bazlı tablo (ekran criticality)\n\n`;
        md += `| Crit | PASS | FAIL | REVIEW | SKIP | Toplam |\n|---|---:|---:|---:|---:|---:|\n`;
        for (const [c, v] of Object.entries(critAgg).sort(([a], [b]) => a.localeCompare(b))) {
            md += `| ${c} | ${v.PASS} | ${v.FAIL} | ${v.REVIEW} | ${v.SKIP} | ${v.total} |\n`;
        }
        md += '\n';

        md += `## 5) P0/P1/P2/P3 Severity Triage\n\n`;
        if (sevAgg.P0 === 0 && sevAgg.P2 === 0) {
            md += `**Hiç finding yok.** PII/token leak yok, module-blocked ekran yok.\n\n`;
        } else {
            if (p0Findings.length) {
                md += `### P0 — PII / token leak (${p0Findings.length})\n`;
                for (const f of p0Findings) {
                    md += `- **[${f.module || 'mobile_smoke_pii_scan'}]** screen=\`${f.screen || f._screen || '-'}\` `;
                    md += `findings=\`${JSON.stringify(f.findings || [])}\`\n  - Test: \`${f._test}\`\n`;
                }
                md += '\n';
            }
            if (p2Findings.length) {
                md += `### P2 — module-blocked / route-missing (${p2Findings.length})\n`;
                for (const f of p2Findings) {
                    md += `- **[mobile_smoke]** screen=\`${f.screen || '-'}\` path=\`${f.path || '-'}\` http=\`${f.http ?? '-'}\`\n`;
                    md += `  - Test: \`${f._test}\`\n  - Network: ${f.detail || '-'}\n`;
                }
                md += '\n';
            }
        }

        md += `## 6) Test failure detayı\n\n`;
        if (failedTests.length === 0) {
            md += `**FAIL yok.** Tüm spec'ler render + console + PII acceptance'ını geçti.\n\n`;
        } else {
            for (const t of failedTests) {
                md += `### ❌ ${t.title}\n`;
                md += `- File: \`${t.file}${t.line ? `:${t.line}` : ''}\`  Süre: ${(t.durationMs / 1000).toFixed(1)}s\n`;
                md += `- Screen: \`${t.screenKey || '-'}\` (\`${t.screenPath || '-'}\`, crit=${t.screenCrit || '-'})\n`;
                md += `- Hata: ${(t.error || '').split('\n').slice(0, 4).join('  ')}\n\n`;
            }
        }

        md += `## 7) Navigasyon performansı (en yavaş 10 ekran)\n\n`;
        const navRows = this.results
            .filter((r) => typeof r.navMs === 'number')
            .sort((a, b) => (b.navMs ?? 0) - (a.navMs ?? 0))
            .slice(0, 10);
        if (navRows.length === 0) {
            md += `_Navigasyon örneği yok._\n\n`;
        } else {
            md += `| Ekran | Path | HTTP | nav (ms) | Durum |\n|---|---|---:|---:|---|\n`;
            for (const r of navRows) {
                md += `| ${r.screenKey || '-'} | ${r.screenPath || '-'} | ${r.httpStatus ?? '-'} | ${r.navMs} | ${r.status} |\n`;
            }
            md += '\n';
        }

        md += `## 8) Test inventory\n\n`;
        md += `| # | Test | Crit | HTTP | Durum | Süre |\n|---:|---|---|---:|---|---:|\n`;
        this.results.forEach((r, i) => {
            const icon = r.status === 'PASS' ? '✅' : r.status === 'SKIP' ? '⏭️' : r.status === 'REVIEW' ? '⚠️' : '❌';
            md += `| ${i + 1} | ${r.title} | ${r.screenCrit || '-'} | ${r.httpStatus ?? '-'} | ${icon} ${r.status} | ${(r.durationMs / 1000).toFixed(1)}s |\n`;
        });
        md += '\n';

        md += `## 9) Artifact path'leri\n\n`;
        md += `- HTML report: \`mobile/e2e/playwright-mobile-smoke-report/\`\n`;
        md += `- JSON results: \`mobile/e2e/playwright-mobile-smoke-report/results.json\`\n`;
        md += `- Trace/video/screenshot: \`mobile/e2e/test-results-mobile-smoke/\`\n\n`;

        md += `## 10) Sonraki tur\n\n`;
        md += `${verdict.next}\n`;

        fs.writeFileSync(outPath, md);
        // eslint-disable-next-line no-console
        console.log(`\n[mobile-smoke-md-reporter] Report yazıldı: ${outPath}`);
    }
}

function decideVerdict({ counters, failedTests, runResult, sevAgg }) {
    const nextStep = 'F10A canlı baseline koşusu (rol secret\'ları + CI dispatch), ardından F10B (mobile auth/biometric)';
    if (sevAgg.P0 > 0) {
        return {
            label: 'NO-GO',
            reason: `P0 finding=${sevAgg.P0} (PII/token leak)`,
            next: `❌ **NO-GO** — baseline öncesi P0 PII leak düzeltilmeli.`,
        };
    }
    if (runResult.status === 'failed' || failedTests.length > 0 || counters.FAIL > 0) {
        return {
            label: 'NO-GO',
            reason: `failedTests=${failedTests.length}, FAIL=${counters.FAIL}`,
            next: `❌ **NO-GO** — baseline öncesi FAIL (boş ekran / console error / render) düzeltilmeli.`,
        };
    }
    if (sevAgg.P2 > 0 || counters.REVIEW > 0) {
        return {
            label: 'GO WITH WATCH',
            reason: `P2=${sevAgg.P2} REVIEW=${counters.REVIEW}`,
            next: `⚠️  **GO WITH WATCH → ${nextStep}** — module-blocked/REVIEW maddeleri izlenecek.`,
        };
    }
    return {
        label: 'GO',
        reason: `Tüm ekranlar render etti, console error=0, PII leak=0, module-blocked=0`,
        next: `✅ **GO → ${nextStep}**`,
    };
}

export default MobileSmokeReporter;
