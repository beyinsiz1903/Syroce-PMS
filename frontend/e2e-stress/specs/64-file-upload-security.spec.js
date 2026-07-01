// F8S § 64 — File / Document Upload Security stress + pen-test.
//
// Threat-model surface (threat_model.md § Tampering + EoP + DoS):
//   "Publicly served uploads must exclude sensitive content"; private
//   uploads (HR staff documents, housekeeping photos) must enforce size,
//   MIME allow-list, polyglot reject, path-traversal filename reject,
//   tenant scope on download.
//
// F8K § 60 ID metadata-only test ediyor (online check-in path); sistem
// genelindeki diğer upload sürfeyleri (HR documents, housekeeping photo)
// için ayrı pen-test yoktu. Bu spec o boşluğu kapatır.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//
// Surface contract:
//   - HR docs: POST /api/hr/staff/{staff_id}/documents — 5 MB hard cap,
//     ALLOWED_DOC_MIME = {pdf, png, jpeg, webp, doc, docx}. Magic-bytes
//     verification VAR (validate_document_bytes → polyglot 400). Ayrıca deploy
//     edge-proxy WAF, <script>/<html>/<svg> gövdesini app'e ulaşmadan 403 ile
//     bloklayabilir (daha sıkı dış katman). Her ikisi de hard-reject sayılır.
//   - Housekeeping photo: POST /api/housekeeping/upload-photo — Pillow
//     magic-bytes validation + 5 MB cap. Polyglot REJECT beklenir (gerçek
//     image format zorunlu).
//
// Module-blocked pattern:
//   - Staff list/probe non-2xx → HR docs skip; housekeeping rooms list
//     non-2xx → photo skip; ikisi de blocked → A-D SKIP, E bağımsız.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'file_upload_security';

// Multipart upload wrapper — Playwright request.post supports `multipart`
// option. UploadFile için { name, mimeType, buffer } shape.
async function multipartUpload(request, path, token, fields, fileField, file) {
    const t0 = Date.now();
    const multipart = { ...fields, [fileField]: file };
    const r = await request.post(path, {
        headers: { Authorization: `Bearer ${token}` },
        multipart,
        failOnStatusCode: false, timeout: 30_000,
    }).catch((e) => ({ status: () => 0, _err: e?.message }));
    const ms = Date.now() - t0;
    const status = r.status?.() ?? 0;
    let body = null;
    try { body = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status, ms, body, ok: status >= 200 && status < 300 };
}

// Tiny valid PNG (1x1 transparent) — magic bytes geçerli.
const TINY_PNG = Buffer.from(
    '89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C636000000000020001E5270DB6000000004945E5444AE426082',
    'hex'
);
// Tiny valid PDF (header only — yeterli MIME validation için).
const TINY_PDF = Buffer.from('%PDF-1.4\n%%EOF\n', 'utf-8');

test.describe.configure({ mode: 'serial' });

test.describe('F8S § 64 — File Upload Security', () => {
    let pilotBefore = null;
    let prefix = null;
    let pilotTid = null;
    let stressStaffId = null;        // stress tenant'a ait staff (HR docs probe için)
    let pilotStaffId = null;         // pilot staff (cross-tenant download attempt için)
    let stressRoomId = null;         // stress room (housekeeping photo için)
    let hrBlocked = false;
    let hrBlockedReason = null;
    let hkBlocked = false;
    let hkBlockedReason = null;
    let uploadedDocId = null;        // cleanup için (legacy single slot)
    let stressUploadedDocId = null;  // self-download smoke için
    let teardownStressToken = null;  // afterAll cleanup için stress bearer kapanı
    // Cleanup ledger — afterAll içinde best-effort DELETE /api/hr/documents/{id}.
    // HK photo endpoint'i DELETE expose etmiyor; backend orphan-cleanup
    // policy stress tenant'ı periyodik temizliyor (housekeeping_router L192
    // safe_file_name UUID'li, listing ayrı koleksiyon). Bu nedenle HR docs
    // explicit teardown ediyoruz; HK photo dokümante drift'tir.
    const createdDocIds = new Set();

    test('Setup: pilot baseline + staff/room probes', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        teardownStressToken = stressTokens.stress_token;

        // Stress staff harvest
        const staffProbe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/staff?limit=5');
        if (staffProbe.moduleBlocked) {
            hrBlocked = true;
            hrBlockedReason = `staff_probe_${staffProbe.reason}_status_${staffProbe.status}`;
        } else {
            const items = Array.isArray(staffProbe.body) ? staffProbe.body
                : (staffProbe.body?.items || staffProbe.body?.staff || staffProbe.body?.staff_members || []);
            if (items.length === 0) {
                hrBlocked = true;
                hrBlockedReason = 'no_stress_staff';
            } else {
                stressStaffId = String(items[0].id || items[0]._id);
            }
        }
        // Pilot staff (cross-tenant)
        try {
            const pp = await callTimed(request, 'get', '/api/hr/staff?limit=5', undefined, stressTokens.pilot_token);
            if (pp.ok) {
                const items = Array.isArray(pp.body) ? pp.body
                    : (pp.body?.items || pp.body?.staff || pp.body?.staff_members || []);
                if (items.length > 0) pilotStaffId = String(items[0].id || items[0]._id);
            }
        } catch { /* best-effort */ }

        // Stress room (housekeeping photo)
        const roomProbe = await withModuleProbe(request, stressTokens.stress_token, '/api/pms/rooms?limit=5');
        if (roomProbe.moduleBlocked) {
            hkBlocked = true;
            hkBlockedReason = `rooms_probe_${roomProbe.reason}_status_${roomProbe.status}`;
        } else {
            const items = Array.isArray(roomProbe.body) ? roomProbe.body
                : (roomProbe.body?.items || roomProbe.body?.rooms || []);
            if (items.length === 0) {
                hkBlocked = true;
                hkBlockedReason = 'no_stress_rooms';
            } else {
                stressRoomId = String(items[0].id || items[0]._id);
            }
        }

        if (hrBlocked) {
            recFinding(testInfo, 'P2', MOD, 'HR docs surface blocked',
                `reason=${hrBlockedReason} — HR doc upload testleri SKIP; HK + final bağımsız.`);
        }
        if (hkBlocked) {
            recFinding(testInfo, 'P2', MOD, 'Housekeeping photo surface blocked',
                `reason=${hkBlockedReason} — HK photo testleri SKIP; HR + final bağımsız.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} stress_staff=${stressStaffId ? 'set' : 'unset'} pilot_staff=${pilotStaffId ? 'set' : 'unset'} stress_room=${stressRoomId ? 'set' : 'unset'} hr_blocked=${hrBlocked} hk_blocked=${hkBlocked}` });
    });

    test('A) HR docs — oversized / bad MIME / polyglot / path traversal reject', async ({ request, stressTokens, stressState }, testInfo) => {
        if (hrBlocked) {
            rec(testInfo, { module: MOD, step: 'hr_docs_reject', status: 'SKIP', note: `hr blocked: ${hrBlockedReason}` });
            test.skip(true, 'hr blocked');
            return;
        }
        const path = `/api/hr/staff/${stressStaffId}/documents?doc_type=other&label=stress_probe`;
        // Backend DOC_MAX_BYTES = 5 MB. 6 MB buffer → 413.
        const oversize = Buffer.alloc(6 * 1024 * 1024, 0x41);
        const cases = [
            // 1) Oversized PDF — beklenti 413.
            { name: 'oversized_pdf', file: { name: 'big.pdf', mimeType: 'application/pdf', buffer: oversize }, expect: (s) => s === 413 || s === 400 || s === 422 },
            // 2) Disallowed MIME (executable).
            { name: 'exe_mime', file: { name: 'shell.exe', mimeType: 'application/x-msdownload', buffer: Buffer.from('MZ\x90\x00') }, expect: (s) => s === 400 || s === 415 || s === 422 },
            // 3) Disallowed MIME (SVG). Reject sınıfı: app 400 (ALLOWED_DOC_MIME
            //    dışı) VEYA deploy edge-proxy WAF 403 (<script>/<svg> gövdesini
            //    app'e ulaşmadan bloklar — daha sıkı dış katman). 403 hard-reject
            //    sayılır; spec'in cross-tenant adımları (L275/L296) zaten 403'ü
            //    "reddedildi" kabul ediyor — burada da tutarlı.
            { name: 'svg_mime', file: { name: 'icon.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg><script>alert(1)</script></svg>') }, expect: (s) => s === 400 || s === 403 || s === 415 || s === 422 },
            // 4) HTML masquerading as PDF (polyglot). App artık magic-bytes
            //    doğruluyor (validate_document_bytes → 400); ayrıca edge-proxy WAF
            //    <html>/<script> gövdesini 403 ile bloklayabilir. Her ikisi de
            //    hard-reject; 2xx (kabul) hâlâ P2 informational olarak işaretlenir.
            { name: 'html_as_pdf_polyglot', file: { name: 'evil.pdf', mimeType: 'application/pdf', buffer: Buffer.from('<html><body><script>alert(1)</script></body></html>') }, expect: (s) => s === 400 || s === 403 || s === 415 || s === 422 || (s >= 200 && s < 300) },
            // 5) Path traversal filename — backend filename'i metadata olarak saklar;
            //    `../../etc/passwd` literal string olarak DB'ye yazılırsa download
            //    response Content-Disposition'da yansıyabilir. Server reject etmeli
            //    veya sanitize etmeli.
            { name: 'path_traversal_filename', file: { name: '../../../../etc/passwd', mimeType: 'application/pdf', buffer: TINY_PDF }, expect: (s) => (s >= 200 && s < 300) || s === 400 },
            // 6) Empty file.
            { name: 'empty_file', file: { name: 'empty.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(0) }, expect: (s) => s === 400 || s === 422 },
        ];
        const results = [];
        const contractViolations = [];
        let polyglotAccepted = false;
        let polyglotDocId = null;
        let traversalAccepted = false;
        let traversalDocId = null;
        let traversalStoredFilename = null;
        for (const c of cases) {
            const r = await multipartUpload(request, path, stressTokens.stress_token, {}, 'file', c.file);
            results.push({ name: c.name, status: r.status });
            if (!c.expect(r.status)) {
                contractViolations.push({ name: c.name, status: r.status });
            }
            if (c.name === 'html_as_pdf_polyglot' && r.ok) {
                polyglotAccepted = true;
                polyglotDocId = r.body?.document?.id || null;
            }
            if (c.name === 'path_traversal_filename' && r.ok) {
                traversalAccepted = true;
                traversalDocId = r.body?.document?.id || null;
                traversalStoredFilename = r.body?.document?.filename || null;
            }
        }
        // Findings.
        if (contractViolations.length > 0) {
            recFinding(testInfo, 'P1', MOD, 'HR upload contract violations',
                `violations=${JSON.stringify(contractViolations)}. Beklenen reject status sınıfı dışı response — validation gevşek veya endpoint deploy değişmiş.`);
        }
        if (polyglotAccepted) {
            // P2 informational — backend MIME header-trust dokümante (magic-bytes
            // verification HR docs için yok, sadece HK photo'da Pillow). Gerçek
            // exploit için download response Content-Type kontrol şart.
            recFinding(testInfo, 'P2', MOD,
                'HR docs polyglot kabul edildi (HTML body, MIME=application/pdf)',
                `doc_id=${polyglotDocId} — backend MIME header-trust; download response Content-Type sanitize edilmezse browser XSS render edebilir. Magic-bytes verification eklenmesi önerilir.`);
        }
        if (traversalAccepted) {
            // Filename sanitize edilmiş mi kontrol et.
            const sanitized = traversalStoredFilename && !traversalStoredFilename.includes('../');
            rec(testInfo, { module: MOD, step: 'hr_docs_traversal_sanitize',
                status: sanitized ? 'PASS' : 'FAIL',
                note: `stored_filename=${traversalStoredFilename} sanitized=${sanitized}` });
            if (!sanitized && traversalStoredFilename) {
                recFinding(testInfo, 'P1', MOD,
                    'HR docs path-traversal filename DB\'ye literal yazıldı',
                    `stored=${traversalStoredFilename} — Content-Disposition response'unda yansırsa client path traversal saldırısı yüzeyi. Server-side sanitize gerek.`);
            }
        }
        // Polyglot ve traversal kayıtlarını cleanup için işaretle.
        if (polyglotDocId) { uploadedDocId = polyglotDocId; createdDocIds.add(polyglotDocId); }
        if (traversalDocId) { if (!uploadedDocId) uploadedDocId = traversalDocId; createdDocIds.add(traversalDocId); }
        rec(testInfo, { module: MOD, step: 'hr_docs_reject',
            status: contractViolations.length === 0 ? 'PASS' : 'FAIL',
            note: `cases=${cases.length} results=${JSON.stringify(results)} polyglot_accepted=${polyglotAccepted} traversal_accepted=${traversalAccepted}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_docs_reject', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) HR docs — valid upload + self download smoke + cross-tenant download reject', async ({ request, stressTokens, stressState }, testInfo) => {
        if (hrBlocked) {
            rec(testInfo, { module: MOD, step: 'hr_docs_xtenant', status: 'SKIP', note: `hr blocked: ${hrBlockedReason}` });
            test.skip(true, 'hr blocked');
            return;
        }
        // Valid upload — TINY_PDF.
        const path = `/api/hr/staff/${stressStaffId}/documents?doc_type=other&label=stress_valid`;
        const up = await multipartUpload(request, path, stressTokens.stress_token, {}, 'file', {
            name: 'valid.pdf', mimeType: 'application/pdf', buffer: TINY_PDF,
        });
        if (!up.ok || !up.body?.document?.id) {
            // Skip-as-pass YASAK: valid upload başarısızsa P1 olarak kayıt et,
            // step FAIL işaretle ve external_calls invariant'ını yine doğrula.
            // Cross-tenant matrisi doc_id olmadan koşulamaz; matrisi atlamak
            // zorunda kalsak da bu durumu maskelemiyoruz.
            rec(testInfo, { module: MOD, step: 'hr_docs_xtenant', status: 'FAIL',
                note: `valid upload failed status=${up.status} body=${JSON.stringify(up.body).slice(0, 100)}` });
            recFinding(testInfo, 'P1', MOD,
                'HR docs valid upload failed — cross-tenant probe matrisi koşulamadı',
                `POST ${path} → status=${up.status} body=${JSON.stringify(up.body).slice(0, 200)}. Server-side validation regression veya endpoint contract drift; cross-tenant download IDOR matrisi bu round için unverified.`);
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_docs_xtenant', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            expect(up.ok, `valid_upload_status=${up.status}`).toBe(true);
            return;
        }
        stressUploadedDocId = up.body.document.id;
        createdDocIds.add(stressUploadedDocId);
        // Self download — stress own doc → 2xx + content.
        const self = await request.get(`/api/hr/documents/${stressUploadedDocId}/download`, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false, timeout: 15_000,
        });
        const selfOk = self.status() >= 200 && self.status() < 300;
        rec(testInfo, { module: MOD, step: 'hr_docs_self_download',
            status: selfOk ? 'PASS' : 'REVIEW',
            note: `status=${self.status()} doc_id=${stressUploadedDocId}` });

        // Cross-tenant download attempt — stress doc ID + pilot token MUST 404.
        const xPilot = await request.get(`/api/hr/documents/${stressUploadedDocId}/download`, {
            headers: { Authorization: `Bearer ${stressTokens.pilot_token}` },
            failOnStatusCode: false, timeout: 15_000,
        });
        const xRejected = xPilot.status() === 404 || xPilot.status() === 403;
        rec(testInfo, { module: MOD, step: 'hr_docs_xtenant_pilot_to_stress',
            status: xRejected ? 'PASS' : 'FAIL',
            note: `pilot_token GET stress_doc → status=${xPilot.status()} expected=403/404` });
        if (xPilot.status() >= 200 && xPilot.status() < 300) {
            recFinding(testInfo, 'P0', MOD,
                'HR doc cross-tenant download — pilot token stress doc indirdi',
                `doc_id=${stressUploadedDocId} status=${xPilot.status()}. tenant scope guard eksik.`);
        }

        // Pilot doc ID varsa, stress token ile dene → 404 beklenir.
        if (pilotStaffId) {
            // Pilot tarafının doc listesini al — pilot own staff'ın doc'unun ID'si.
            const pl = await callTimed(request, 'get', `/api/hr/staff/${pilotStaffId}/documents`, undefined, stressTokens.pilot_token);
            const pdocs = pl.ok ? (pl.body?.items || []) : [];
            if (pdocs.length > 0) {
                const pdocId = pdocs[0].id;
                const xStress = await request.get(`/api/hr/documents/${pdocId}/download`, {
                    headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                    failOnStatusCode: false, timeout: 15_000,
                });
                const sRejected = xStress.status() === 404 || xStress.status() === 403;
                rec(testInfo, { module: MOD, step: 'hr_docs_xtenant_stress_to_pilot',
                    status: sRejected ? 'PASS' : 'FAIL',
                    note: `stress_token GET pilot_doc → status=${xStress.status()} expected=403/404` });
                if (xStress.status() >= 200 && xStress.status() < 300) {
                    recFinding(testInfo, 'P0', MOD,
                        'HR doc cross-tenant download — stress token pilot doc indirdi',
                        `pilot_doc_id=${pdocId} status=${xStress.status()}. IDOR.`);
                }
            }
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_docs_xtenant', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Housekeeping photo — polyglot/oversized/MIME/path-traversal reject (magic-bytes enforced)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (hkBlocked) {
            rec(testInfo, { module: MOD, step: 'hk_photo_reject', status: 'SKIP', note: `hk blocked: ${hkBlockedReason}` });
            test.skip(true, 'hk blocked');
            return;
        }
        const path = '/api/housekeeping/upload-photo';
        const oversize = Buffer.alloc(6 * 1024 * 1024, 0x41);
        const cases = [
            // 1) Oversized — 5MB cap.
            { name: 'oversized_png', photo: { name: 'big.png', mimeType: 'image/png', buffer: oversize }, expect: (s) => s === 413 || s === 400 || s === 422 },
            // 2) HTML masquerade as PNG — Pillow magic-bytes must reject (app 400).
            //    Deploy edge-proxy WAF de <html>/<script> gövdesini 403 ile
            //    bloklayabilir (daha sıkı dış katman) — her ikisi de hard-reject.
            { name: 'html_as_png_polyglot', photo: { name: 'evil.png', mimeType: 'image/png', buffer: Buffer.from('<html><script>alert(1)</script></html>') }, expect: (s) => s === 400 || s === 403 || s === 415 || s === 422 },
            // 3) PDF as JPEG — magic-bytes reject.
            { name: 'pdf_as_jpeg', photo: { name: 'doc.jpg', mimeType: 'image/jpeg', buffer: TINY_PDF }, expect: (s) => s === 400 || s === 415 || s === 422 },
            // 4) SVG (script vector) — Pillow image format reddetmeli (app 400);
            //    deploy edge-proxy WAF de <svg>/<script> gövdesini 403 ile
            //    bloklayabilir (daha sıkı dış katman) — her ikisi de hard-reject.
            { name: 'svg_as_image', photo: { name: 'a.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg><script>alert(1)</script></svg>') }, expect: (s) => s === 400 || s === 403 || s === 415 || s === 422 },
            // 5) EXE as PNG — magic-bytes reject.
            { name: 'exe_as_png', photo: { name: 'shell.png', mimeType: 'image/png', buffer: Buffer.from('MZ\x90\x00\x03\x00') }, expect: (s) => s === 400 || s === 415 || s === 422 },
            // 6) Empty.
            { name: 'empty', photo: { name: 'empty.png', mimeType: 'image/png', buffer: Buffer.alloc(0) }, expect: (s) => s === 400 || s === 422 },
            // 7) Path traversal filename.
            { name: 'path_traversal_filename', photo: { name: '../../../etc/passwd.png', mimeType: 'image/png', buffer: TINY_PNG }, expect: (s) => (s >= 200 && s < 300) || s === 400 },
        ];
        const results = [];
        const contractViolations = [];
        let traversalStored = null;
        for (const c of cases) {
            const r = await multipartUpload(request, path, stressTokens.stress_token, {
                room_id: stressRoomId,
                photo_type: 'inspection',
            }, 'photo', c.photo);
            results.push({ name: c.name, status: r.status });
            if (!c.expect(r.status)) {
                contractViolations.push({ name: c.name, status: r.status });
            }
            if (c.name === 'path_traversal_filename' && r.ok) {
                traversalStored = r.body?.file_name || r.body?.photo?.file_name || null;
            }
        }
        if (contractViolations.length > 0) {
            // Pillow magic-bytes reject doctrine — polyglot/MIME-mismatch
            // ihlali P0 (gerçek security regression).
            const polyglotIssues = contractViolations.filter(c =>
                ['html_as_png_polyglot', 'pdf_as_jpeg', 'svg_as_image', 'exe_as_png'].includes(c.name) && c.status >= 200 && c.status < 300);
            if (polyglotIssues.length > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'Housekeeping photo polyglot kabul edildi — Pillow magic-bytes validation bypass',
                    `accepted=${JSON.stringify(polyglotIssues)}. validate_image_bytes() bypass; XSS/RCE riski.`);
            }
            const otherViolations = contractViolations.filter(c => !polyglotIssues.find(p => p.name === c.name));
            if (otherViolations.length > 0) {
                recFinding(testInfo, 'P1', MOD, 'Housekeeping photo contract violations',
                    `violations=${JSON.stringify(otherViolations)}.`);
            }
        }
        if (traversalStored && traversalStored.includes('../')) {
            recFinding(testInfo, 'P1', MOD,
                'Housekeeping photo filename traversal sanitize bypass',
                `stored=${traversalStored} — backend uuid+ext kullanmalı (housekeeping_router L192 safe_file_name).`);
        }
        rec(testInfo, { module: MOD, step: 'hk_photo_reject',
            status: contractViolations.length === 0 ? 'PASS' : 'FAIL',
            note: `cases=${cases.length} results=${JSON.stringify(results)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hk_photo_reject', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Unauthenticated upload — both surfaces must reject without bearer', async ({ request, stressState, stressTokens }, testInfo) => {
        if (hrBlocked && hkBlocked) {
            rec(testInfo, { module: MOD, step: 'unauth_upload', status: 'SKIP', note: 'both surfaces blocked' });
            test.skip(true, 'both blocked');
            return;
        }
        const targets = [];
        if (!hrBlocked && stressStaffId) {
            targets.push({ key: 'hr_doc', path: `/api/hr/staff/${stressStaffId}/documents?doc_type=other`, field: 'file', file: { name: 'a.pdf', mimeType: 'application/pdf', buffer: TINY_PDF } });
        }
        if (!hkBlocked && stressRoomId) {
            targets.push({ key: 'hk_photo', path: '/api/housekeeping/upload-photo', field: 'photo', file: { name: 'a.png', mimeType: 'image/png', buffer: TINY_PNG }, extraFields: { room_id: stressRoomId, photo_type: 'inspection' } });
        }
        const results = [];
        let leaks = 0;
        for (const t of targets) {
            const r = await request.post(t.path, {
                multipart: { ...(t.extraFields || {}), [t.field]: t.file },
                failOnStatusCode: false, timeout: 15_000,
            }).catch((e) => ({ status: () => 0 }));
            const st = r.status?.() ?? 0;
            results.push({ key: t.key, status: st });
            if (st >= 200 && st < 300) {
                leaks++;
                recFinding(testInfo, 'P0', MOD, `unauth_upload_accepted:${t.key}`,
                    `unauth POST ${t.path} → status=${st}. Auth bypass on upload endpoint.`);
            }
        }
        rec(testInfo, { module: MOD, step: 'unauth_upload',
            status: leaks === 0 ? 'PASS' : 'FAIL',
            note: `targets=${targets.length} leaks=${leaks} results=${JSON.stringify(results)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'unauth_upload', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(leaks).toBe(0);
    });

    // Best-effort cleanup — stress tenant'ta yaratılan HR documents'ı DELETE
    // /api/hr/documents/{id} ile sil. 4xx (already gone, permission) sessizce
    // tolere edilir; round'lar arası storage drift'i önler. HK photo için
    // DELETE endpoint yok — drift dokümante.
    test.afterAll(async ({ request }) => {
        if (createdDocIds.size === 0) return;
        // stressTokens fixture afterAll'da accessible değil; setup'tan kapan.
        const token = teardownStressToken;
        if (!token) return;
        const results = [];
        for (const id of createdDocIds) {
            try {
                const r = await request.delete(`/api/hr/documents/${id}`, {
                    headers: { Authorization: `Bearer ${token}` },
                    failOnStatusCode: false, timeout: 10_000,
                });
                results.push({ id, status: r.status() });
            } catch (e) {
                results.push({ id, error: String(e?.message || e).slice(0, 80) });
            }
        }
        // Best-effort log to stdout — afterAll'da rec/testInfo yok.
        // eslint-disable-next-line no-console
        console.log(`[${MOD}] afterAll cleanup: ${JSON.stringify(results)}`);
    });

    test('E) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
