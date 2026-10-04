#!/usr/bin/env node
/**
 * Keeps the five operationally-critical routes from quietly regaining a large
 * lazy chunk.  Network timing is checked in Playwright; this check is the
 * deterministic companion that catches a size regression before browser or
 * backend variance can hide it.
 */
import { gzipSync } from 'node:zlib';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const buildDir = path.resolve('build/js');
const outputPath = path.resolve('build/performance-route-bundle-budgets.json');

// Budgets are gzip bytes for each route's own lazy chunk. Shared vendor bytes
// are intentionally measured by e2e/performance-budgets.spec.js per route.
const ROUTE_BUDGETS = [
  { route: 'dashboard', pattern: /^Dashboard-.*\.js$/, maxGzipBytes: 18 * 1024 },
  { route: 'pms', pattern: /^PMSModule-.*\.js$/, maxGzipBytes: 40 * 1024 },
  { route: 'calendar', pattern: /^ReservationCalendar-.*\.js$/, maxGzipBytes: 45 * 1024 },
  { route: 'reports', pattern: /^BasicReports-.*\.js$/, maxGzipBytes: 40 * 1024 },
  { route: 'channel-manager', pattern: /^ChannelManagerModule-.*\.js$/, maxGzipBytes: 16 * 1024 },
];

const files = await readdir(buildDir);
const results = [];
const failures = [];

for (const budget of ROUTE_BUDGETS) {
  const matchingFile = files.find((file) => budget.pattern.test(file));
  if (!matchingFile) {
    failures.push(`${budget.route}: route chunk not found`);
    continue;
  }

  const source = await readFile(path.join(buildDir, matchingFile));
  const gzipBytes = gzipSync(source).byteLength;
  const result = {
    route: budget.route,
    file: matchingFile,
    gzipBytes,
    maxGzipBytes: budget.maxGzipBytes,
    ok: gzipBytes <= budget.maxGzipBytes,
  };
  results.push(result);
  if (!result.ok) {
    failures.push(`${budget.route}: ${gzipBytes} B exceeds ${budget.maxGzipBytes} B`);
  }
}

await writeFile(outputPath, `${JSON.stringify({ schemaVersion: 1, results }, null, 2)}\n`);
for (const result of results) {
  const verdict = result.ok ? 'PASS' : 'FAIL';
  console.log(`[${verdict}] ${result.route}: ${(result.gzipBytes / 1024).toFixed(1)} KiB / ${(result.maxGzipBytes / 1024).toFixed(1)} KiB (${result.file})`);
}

if (failures.length > 0) {
  console.error(`\nRoute bundle budget failures:\n- ${failures.join('\n- ')}`);
  process.exitCode = 1;
}
