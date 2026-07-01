// ─────────────────────────────────────────────────────────────────────────
// Custom Playwright reporter — Markdown drill report.
// ─────────────────────────────────────────────────────────────────────────
// Çıktı: <repo>/docs/drill_reports/YYYYMMDD_ui_e2e_smoke.md
//
// Rapor içeriği:
//   - Özet tablosu (toplam / pass / fail / skipped, süre)
//   - Failed steps listesi (sayfa + path + reason + console/network örnek)
//   - Tüm route'ların matrisı (desktop + mobile)
//   - Trace/screenshot/video artefakt path'leri
// ─────────────────────────────────────────────────────────────────────────

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Bu dosya: <repo>/frontend/e2e-smoke/markdown-reporter.js
// Repo root = bu dosyanın iki üstü (`../..`). cwd-bağımsız çıktı yolu için
// import.meta.url'den derive ediyoruz; CI wrapper farklı cwd'de koşsa bile
// rapor her zaman <repo>/docs/drill_reports/ altına düşer.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');

class MarkdownReporter {
    constructor(options = {}) {
        this.options = options;
        this.results = [];
        this.startTime = Date.now();
    }

    onBegin(config, suite) {
        this.config = config;
        this.totalTests = suite.allTests().length;
    }

    onTestEnd(test, result) {
        const annotations = {};
        for (const a of test.annotations || []) {
            annotations[a.type] = a.description;
        }
        for (const a of result.annotations || []) {
            annotations[a.type] = a.description;
        }
        this.results.push({
            title: test.title,
            project: test.parent?.project?.()?.name || (test.titlePath()[1] || 'default'),
            file: test.location?.file || '',
            status: result.status,
            duration: result.duration,
            error: result.error?.message || result.errors?.[0]?.message || '',
            annotations,
            attachments: (result.attachments || []).map((a) => ({
                name: a.name,
                contentType: a.contentType,
                path: a.path,
            })),
        });
    }

    async onEnd(result) {
        const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const reportDir = path.join(REPO_ROOT, 'docs', 'drill_reports');
        try {
            fs.mkdirSync(reportDir, { recursive: true });
        } catch {
            /* dir may already exist */
        }
        const reportPath = path.join(reportDir, `${stamp}_ui_e2e_smoke.md`);

        const md = this.renderMarkdown(result);
        fs.writeFileSync(reportPath, md, 'utf-8');

        // stdout banner — CI log'unda görünür olsun
        // eslint-disable-next-line no-console
        console.log(`\n[smoke-md-reporter] Report yazıldı: ${reportPath}\n`);
    }

    renderMarkdown(result) {
        const totalSec = ((Date.now() - this.startTime) / 1000).toFixed(1);
        const counts = { passed: 0, failed: 0, skipped: 0, timedOut: 0, interrupted: 0 };
        for (const r of this.results) counts[r.status] = (counts[r.status] || 0) + 1;
        const total = this.results.length;

        const failed = this.results.filter((r) => r.status === 'failed' || r.status === 'timedOut');
        const passed = this.results.filter((r) => r.status === 'passed');

        const verdict = failed.length === 0 ? '✅ PASS' : '❌ FAIL';
        const baseUrl = process.env.E2E_BASE_URL || '(unset)';
        const adminEmail = process.env.E2E_ADMIN_EMAIL ? maskEmail(process.env.E2E_ADMIN_EMAIL) : '(unset)';

        const lines = [];
        lines.push(`# UI E2E Smoke Report`);
        lines.push('');
        lines.push(`**Verdict:** ${verdict}`);
        lines.push(`**Generated:** ${new Date().toISOString()}`);
        lines.push(`**Base URL:** \`${baseUrl}\``);
        lines.push(`**Admin:** \`${adminEmail}\``);
        lines.push(`**Duration:** ${totalSec}s`);
        lines.push('');
        lines.push(`## Özet`);
        lines.push('');
        lines.push(`| Metric | Count |`);
        lines.push(`|---|---|`);
        lines.push(`| Total | ${total} |`);
        lines.push(`| Passed | ${counts.passed || 0} |`);
        lines.push(`| Failed | ${counts.failed || 0} |`);
        lines.push(`| Timed out | ${counts.timedOut || 0} |`);
        lines.push(`| Skipped | ${counts.skipped || 0} |`);
        lines.push('');

        if (failed.length) {
            lines.push(`## ❌ Failed Steps (${failed.length})`);
            lines.push('');
            for (const f of failed) {
                lines.push(`### ${f.title}`);
                lines.push('');
                lines.push(`- **Project:** ${f.project}`);
                lines.push(`- **Path:** \`${f.annotations['route-path'] || '-'}\``);
                lines.push(`- **HTTP:** ${f.annotations['http-status'] || '-'}`);
                lines.push(`- **Inspect:** ${f.annotations['inspect'] || '-'}`);
                lines.push(`- **Console errors:** ${f.annotations['console-errors-count'] || '0'}`);
                lines.push(`- **Network errors:** ${f.annotations['network-errors-count'] || '0'}`);
                lines.push(`- **Duration:** ${(f.duration / 1000).toFixed(1)}s`);
                if (f.error) {
                    lines.push('');
                    lines.push('**Error:**');
                    lines.push('```');
                    lines.push(truncate(stripAnsi(f.error), 1200));
                    lines.push('```');
                }
                if (f.annotations['console-errors']) {
                    lines.push('');
                    lines.push('**Console error sample:**');
                    lines.push('```json');
                    lines.push(truncate(f.annotations['console-errors'], 800));
                    lines.push('```');
                }
                if (f.annotations['network-errors']) {
                    lines.push('');
                    lines.push('**Network error sample:**');
                    lines.push('```json');
                    lines.push(truncate(f.annotations['network-errors'], 800));
                    lines.push('```');
                }
                if (f.attachments.length) {
                    lines.push('');
                    lines.push('**Artifacts:**');
                    for (const a of f.attachments) {
                        const rel = a.path ? path.relative(REPO_ROOT, a.path) : '(inline)';
                        lines.push(`- ${a.name} (${a.contentType || '-'}): \`${rel}\``);
                    }
                }
                lines.push('');
            }
        } else {
            lines.push(`## ✅ Failed Steps`);
            lines.push('');
            lines.push('_Hiç failed step yok._');
            lines.push('');
        }

        lines.push(`## Tüm Route Matrisı`);
        lines.push('');
        lines.push(`| Status | Project | Sayfa | Path | HTTP | Console | Network | Süre |`);
        lines.push(`|---|---|---|---|---|---|---|---|`);
        for (const r of this.results) {
            const icon = r.status === 'passed' ? '✓' : r.status === 'failed' ? '✗' : r.status === 'skipped' ? '○' : '⚠';
            const cleanTitle = r.title.replace(/^\[(CRITICAL|secondary)\]\s*/, '');
            lines.push(
                `| ${icon} ${r.status} | ${r.project} | ${cleanTitle.split(' (')[0]} | \`${r.annotations['route-path'] || '-'}\` | ${r.annotations['http-status'] || '-'} | ${r.annotations['console-errors-count'] || '0'} | ${r.annotations['network-errors-count'] || '0'} | ${(r.duration / 1000).toFixed(1)}s |`
            );
        }
        lines.push('');

        // Safe-click özeti — neyi tıklamayı denedik?
        const withClicks = this.results.filter((r) => r.annotations['safe-clicks']);
        if (withClicks.length) {
            lines.push(`## Güvenli Buton Tıklamaları`);
            lines.push('');
            lines.push(`| Sayfa | Tıklanan Butonlar |`);
            lines.push(`|---|---|`);
            for (const r of withClicks) {
                const cleanTitle = r.title.replace(/^\[(CRITICAL|secondary)\]\s*/, '');
                lines.push(`| ${cleanTitle.split(' (')[0]} | ${r.annotations['safe-clicks']} |`);
            }
            lines.push('');
        }

        lines.push('---');
        lines.push('');
        lines.push('_Generated by `frontend/e2e-smoke/markdown-reporter.js`._');
        lines.push('');
        return lines.join('\n');
    }
}

function stripAnsi(s) {
    // eslint-disable-next-line no-control-regex
    return String(s).replace(/\x1b\[[0-9;]*m/g, '');
}

function truncate(s, n) {
    const v = String(s);
    return v.length > n ? `${v.slice(0, n)}…[truncated]` : v;
}

function maskEmail(s) {
    const [u, d] = String(s).split('@');
    if (!d) return '***';
    return `${u.slice(0, 2)}***@${d}`;
}

export default MarkdownReporter;
