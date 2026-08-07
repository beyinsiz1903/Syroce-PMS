import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { decideVerdict } from './markdown-reporter.mjs';
import { resolveSpecPatterns } from './resolve-spec-patterns.mjs';

const directory = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(directory, '..');
const repositoryRoot = path.resolve(frontendRoot, '..');
const shardBPatterns = [
    'e2e-stress/specs/02-*.spec.js',
    'e2e-stress/specs/03-*.spec.js',
    'e2e-stress/specs/04-*.spec.js',
    'e2e-stress/specs/05-*.spec.js',
    'e2e-stress/specs/06-*.spec.js',
    'e2e-stress/specs/09-*.spec.js',
    'e2e-stress/specs/95-*.spec.js',
    'e2e-stress/specs/99-*.spec.js',
    'e2e-stress/specs/99B-*.spec.js',
];

test('Shard B patterns resolve to the eleven configured spec files', () => {
    const resolved = resolveSpecPatterns(shardBPatterns, { cwd: frontendRoot });

    assert.deepEqual(resolved, [
        'e2e-stress/specs/02-day-turnover.spec.js',
        'e2e-stress/specs/03-room-move.spec.js',
        'e2e-stress/specs/04-folio-mass.spec.js',
        'e2e-stress/specs/05-reservation-lifecycle.spec.js',
        'e2e-stress/specs/06-night-audit.spec.js',
        'e2e-stress/specs/09-ops-readiness-smoke.spec.js',
        'e2e-stress/specs/95-reservation-lifecycle-deep.spec.js',
        'e2e-stress/specs/99-finance-folio-surface.spec.js',
        'e2e-stress/specs/99-full-24h-hotel-simulation.spec.js',
        'e2e-stress/specs/99-pos-extensions.spec.js',
        'e2e-stress/specs/99B-folio-split-surface.spec.js',
    ]);
});

test('Shard B files declare the expected 116 Playwright tests', () => {
    const resolved = resolveSpecPatterns(shardBPatterns, { cwd: frontendRoot });
    const declarationCount = resolved.reduce((total, relativePath) => {
        const source = fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8');
        return total + (source.match(/^\s*test\(/gm)?.length || 0);
    }, 0);

    assert.equal(declarationCount, 116);
});

test('zero-match and unsafe patterns fail closed', () => {
    assert.throws(
        () => resolveSpecPatterns(['e2e-stress/specs/does-not-exist-*.spec.js'], { cwd: frontendRoot }),
        /BLOCKED_TEST_DISCOVERY: pattern matched zero files/,
    );
    assert.throws(
        () => resolveSpecPatterns(['../e2e-stress/specs/02-*.spec.js'], { cwd: frontendRoot }),
        /BLOCKED_TEST_DISCOVERY: unsafe spec pattern/,
    );
});

test('zero executed tests can never produce a GO verdict', () => {
    const verdict = decideVerdict({
        counters: { PASS: 0, FAIL: 0, REVIEW: 0, SKIP: 0 },
        failedTests: [],
        runResult: { status: 'passed' },
        state: null,
        teardown: null,
        sevAgg: { P0: 0, P1: 0, P2: 0, P3: 0 },
        testCount: 0,
    });

    assert.equal(verdict.label, 'NO-GO');
    assert.match(verdict.reason, /BLOCKED_TEST_DISCOVERY/);
});

test('stress workflow inventories resolved files and hard-fails zero tests', () => {
    const workflow = fs.readFileSync(path.join(repositoryRoot, '.github/workflows/stress.yml'), 'utf8');

    assert.match(workflow, /node e2e-stress\/resolve-spec-patterns\.mjs/);
    assert.match(workflow, /BLOCKED_TEST_DISCOVERY/);
    assert.match(workflow, /--list/);
    assert.match(workflow, /FULL_DISCOVERED_TEST_COUNT/);
    assert.match(workflow, /DISCOVERED_TEST_COUNT/);
    assert.match(workflow, /EXECUTED_TEST_COUNT/);
    assert.match(workflow, /STRESS_TEARDOWN_LOG_NAME: 'teardown\.json'/);
    assert.match(workflow, /test -s e2e-stress\/\.auth\/teardown\.json/);
});

test('stress config keeps the guarded setup, teardown, and single project', () => {
    const config = fs.readFileSync(path.join(frontendRoot, 'playwright.stress.config.js'), 'utf8');
    const context = fs.readFileSync(path.join(directory, 'fixtures/stress-context.js'), 'utf8');

    assert.match(config, /testDir:\s*'\.\/e2e-stress\/specs'/);
    assert.match(config, /globalSetup:.*global-setup\.js/);
    assert.match(config, /globalTeardown:.*global-teardown\.js/);
    assert.match(config, /name:\s*'stress'/);
    assert.doesNotMatch(config, /testMatch:|testIgnore:|grep:|grepInvert:/);
    assert.match(context, /apiBaseUrl:\s*async \(\{ baseURL \}, use\)/);
});
