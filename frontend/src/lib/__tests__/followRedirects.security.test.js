// @vitest-environment node
// Loopback-only regression for GHSA-mrwp-f3q8-3g9p. No real credentials.
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const redirects = require('follow-redirects');
const installed = require('follow-redirects/package.json');
const manifest = JSON.parse(readFileSync(new URL('../../../package.json', import.meta.url), 'utf8'));
const npmLock = JSON.parse(readFileSync(new URL('../../../package-lock.json', import.meta.url), 'utf8'));
let source;
let destination;
let sourceUrl;

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.removeListener('error', reject);
      resolve(`http://127.0.0.1:${server.address().port}`);
    });
  });
}

function close(server) {
  if (!server?.listening) return Promise.resolve();
  server.closeAllConnections();
  return new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}

function getHeaders(path, headers, sensitiveHeaders) {
  return new Promise((resolve, reject) => {
    const request = redirects.http.get(`${sourceUrl}${path}`, {
      headers, sensitiveHeaders, maxRedirects: 3,
    }, response => {
      let data = '';
      response.setEncoding('utf8');
      response.on('data', chunk => { data += chunk; });
      response.on('error', reject);
      response.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (error) { reject(error); }
      });
    });
    request.on('error', reject);
    request.setTimeout(2000, () => request.destroy(new Error('Local redirect test timed out')));
  });
}

describe('follow-redirects security floor and credential boundaries', () => {
  beforeAll(async () => {
    destination = http.createServer((request, response) => {
      response.end(JSON.stringify(request.headers));
    });
    const destinationUrl = await listen(destination);
    source = http.createServer((request, response) => {
      if (request.url === '/same-target') {
        response.end(JSON.stringify(request.headers));
        return;
      }
      response.writeHead(302, { Location: request.url === '/same' ? '/same-target' : destinationUrl });
      response.end();
    });
    sourceUrl = await listen(source);
  });

  afterAll(async () => { await Promise.all([close(source), close(destination)]); });

  it('pins the installed package and both package-manager paths to the patched release', () => {
    expect(installed.version).toBe('1.16.2');
    expect(manifest.resolutions['follow-redirects']).toBe('1.16.2');
    expect(manifest.overrides['follow-redirects']).toBe('1.16.2');
    expect(npmLock.packages['node_modules/follow-redirects'].version).toBe('1.16.2');
    const yarnLock = readFileSync(new URL('../../../yarn.lock', import.meta.url), 'utf8');
    expect(yarnLock).toMatch(/follow-redirects@[^\n]+:\n {2}version "1\.16\.2"/);
  });

  it.each([
    ['same-realm list and object headers', false, false],
    ['cross-realm list and object headers', true, false],
    ['cross-realm list and array-form headers', true, true],
  ])('strips a custom sensitive credential across origins: %s', async (_name, crossRealm, arrayHeaders) => {
    const names = crossRealm ? runInNewContext("['X-QA-Credential']") : ['X-QA-Credential'];
    if (crossRealm) {
      expect(Array.isArray(names)).toBe(true);
      expect(names instanceof Array).toBe(false);
    }
    const headers = arrayHeaders
      ? ['X-QA-Credential', 'synthetic-only', 'X-Harmless', 'keep-me']
      : { 'X-QA-Credential': 'synthetic-only', 'X-Harmless': 'keep-me' };
    const received = await getHeaders('/cross', headers, names);
    expect(received['x-qa-credential']).toBeUndefined();
    expect(received['x-harmless']).toBe('keep-me');
  });

  it('retains built-in Authorization and Cookie protections across origins', async () => {
    const received = await getHeaders('/cross', {
      Authorization: 'synthetic-only', Cookie: 'qa=synthetic', 'X-Harmless': 'keep-me',
    }, []);
    expect(received.authorization).toBeUndefined();
    expect(received.cookie).toBeUndefined();
    expect(received['x-harmless']).toBe('keep-me');
  });

  it('preserves the declared custom header on a same-origin redirect', async () => {
    const received = await getHeaders('/same', { 'X-QA-Credential': 'synthetic-only' },
      runInNewContext("['X-QA-Credential']"));
    expect(received['x-qa-credential']).toBe('synthetic-only');
  });
});
