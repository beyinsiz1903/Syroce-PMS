import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const directory = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(directory, '..');
const repositoryRoot = path.resolve(frontendRoot, '..');

function readRepositoryFile(relativePath) {
    return fs.readFileSync(path.join(repositoryRoot, relativePath), 'utf8');
}

test('HotelRunner stress signing secret uses the isolated fixture lifecycle', () => {
    const workflow = readRepositoryFile('.github/workflows/stress.yml');
    const setup = readRepositoryFile('frontend/e2e-stress/global-setup.js');
    const stressRouter = readRepositoryFile('backend/domains/admin/router/stress.py');

    assert.match(workflow, /HOTELRUNNER_WEBHOOK_SECRET:\s*\$\{\{ secrets\.STRESS_HOTELRUNNER_WEBHOOK_SECRET \}\}/);
    assert.match(setup, /if \(!hotelRunnerWebhookSecret\)[\s\S]*HotelRunner signing configuration missing/);
    assert.match(setup, /hotelrunner_webhook_secret:\s*hotelRunnerWebhookSecret/);
    assert.match(setup, /if \(!seedResp\.ok\(\)\)[\s\S]*\/api\/admin\/stress\/cleanup/);
    assert.doesNotMatch(setup, /seed failed \(\$\{seedResp\.status\(\)\}\): \$\{txt/);
    assert.match(stressRouter, /hotelrunner_webhook_secret:\s*SecretStr \| None = None/);
    assert.match(stressRouter, /store_webhook_secret\([\s\S]*actor="stress_seed"/);
    assert.match(stressRouter, /delete_webhook_secret\([\s\S]*actor="stress_cleanup"/);
});

test('public room QR stress creates a guest session before submit', () => {
    const source = readRepositoryFile('frontend/e2e-stress/specs/10-qr-requests.spec.js');

    assert.match(source, /\/api\/public\/room-qr\/\$\{stressTid\}\/\$\{room\.id\}\/session/);
    assert.match(source, /'X-Guest-Session': sessionToken/);
    assert.match(source, /expect\(target\.length,[\s\S]*\)\.toBe\(50\)/);
    assert.doesNotMatch(source, /not enough rooms.*status: 'SKIP'/);
});

test('Quick-ID public stress probes remain local and fail on unavailable service', () => {
    const proxy = readRepositoryFile('backend/routers/quick_id_proxy.py');
    const stressSpec = readRepositoryFile('frontend/e2e-stress/specs/60-public-online-checkin.spec.js');

    assert.match(proxy, /TOKEN_PATTERN = r"\^\[A-Za-z0-9_-\]\{16,128\}\$"/);
    assert.match(proxy, /QUICKID_PUBLIC_INFO_TIMEOUT = min\(QUICKID_UPSTREAM_TIMEOUT, 5\.0\)/);
    assert.match(stressSpec, /'A'\.repeat\(129\)/);
    assert.match(stressSpec, /too-short-token/);
    assert.match(stressSpec, /controlled upstream unavailability is FAIL, never PASS\/REVIEW\/SKIP/);
    assert.match(stressSpec, /QUICKID_UNAVAILABLE[\s\S]*\)\.finalStatus\)\.toBe\('FAIL'\)/);
});
