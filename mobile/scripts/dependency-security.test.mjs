import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { runInNewContext } from 'node:vm';

const require = createRequire(import.meta.url);
const decoder = require('decode-uri-component');
const query = require('query-string');
const queryRequire = createRequire(require.resolve('query-string'));
const expoRequire = createRequire(require.resolve('expo/package.json'));
const cliRoot = dirname(expoRequire.resolve('@expo/cli/package.json'));

test('patched decoder preserves the CommonJS contract and upstream algorithm', () => {
  assert.equal(typeof decoder, 'function');
  assert.equal(queryRequire.resolve('decode-uri-component'), require.resolve('decode-uri-component'));
  const source = readFileSync(require.resolve('decode-uri-component'), 'utf8')
    .replace('module.exports = function decodeUriComponent(encodedURI) {',
      'export default function decodeUriComponent(encodedURI) {');
  assert.equal(createHash('sha256').update(source.trimEnd() + '\n').digest('hex'),
    '6a86ac891edf15c5efa0841ebb31935e3669d58b98318b57d7b08a4530317cb0');
});

test('router query dependency preserves Turkish, repeated params and single decoding', () => {
  const parsed = query.parse('name=%C4%B0stanbul+%C5%9Eube&tag=oda&tag=folyo&next=%252Fcashier');
  assert.equal(parsed.name, 'İstanbul Şube');
  assert.deepEqual(parsed.tag, ['oda', 'folyo']);
  assert.equal(parsed.next, '%2Fcashier');
  assert.deepEqual(query.parse(query.stringify(parsed)), parsed);
  assert.equal(query.parse('bad=%E0%A4%A&ok=%C3%A7').ok, 'ç');
});

test('malformed URI compatibility and input type guard', () => {
  for (const value of ['%', '%G0', '%80', '%C0%AF', '%E0%A4%A', '%F4%90%80%80']) {
    assert.equal(typeof decoder(value), 'string');
  }
  assert.equal(decoder('%FE%FF'), '\uFFFD\uFFFD');
  assert.equal(decoder('%C2'), '\uFFFD');
  assert.equal(decoder('%2520'), '%20');
  assert.throws(() => decoder(null), TypeError);
});

test('large malformed percent run is bounded in an isolated process', () => {
  const child = spawnSync(process.execPath, ['-e',
    "const d=require(process.argv[1]);const s='%80'.repeat(100000);if(d(s)!==s)process.exit(2)",
    require.resolve('decode-uri-component')], { timeout: 5000, encoding: 'utf8' });
  assert.equal(child.error, undefined);
  assert.equal(child.status, 0, child.stderr);
});

test('patched glob dependency preserves matching and traversal contracts', async () => {
  const { minimatch, Minimatch } = require('minimatch');
  assert.equal(minimatch('src/rooms.tsx', 'src/**/*.{ts,tsx}'), true);
  assert.equal(new Minimatch('**/*.js').match('app/room.js'), true);
  const { glob, globSync } = require('glob');
  const options = { cwd: join(dirname(new URL(import.meta.url).pathname), '..'), nodir: true };
  const pattern = 'scripts/*security.test.mjs';
  assert.deepEqual(globSync(pattern, options), ['scripts/dependency-security.test.mjs']);
  assert.deepEqual(await glob(pattern, options), ['scripts/dependency-security.test.mjs']);
  const controller = new AbortController();
  controller.abort(new Error('synthetic-abort'));
  await assert.rejects(glob('**/*', { ...options, signal: controller.signal }), /synthetic-abort/);
});

test('Expo devtools validates plugin/output schemas and MCP parameters with Zod 4', () => {
  const { PluginSchema, DevToolsPluginOutputSchema } = require(join(cliRoot,
    'build/src/start/server/devtools/DevToolsPlugin.schema.js'));
  const { createMCPDevToolsExtensionSchema } = require(join(cliRoot,
    'build/src/start/server/mcp/createMCPDevToolsExtensionSchema.js'));
  // The SDK57 patch uses JSON Schema for plugins/output and takes the MCP
  // host's Zod instance explicitly. Exercise the installed validators rather
  // than relying on the previous CLI's internal Zod-schema representation.
  const cliRequire = createRequire(join(cliRoot, 'package.json'));
  const { validate, ValidationError } = cliRequire('@expo/schema-utils');
  const { z } = require('zod');
  const plugin = {
    packageName: 'synthetic-devtool', packageRoot: '/synthetic',
    cliExtensions: { description: 'local compatibility check', entryPoint: 'index.js',
      commands: [{ name: 'inspect', title: 'Inspect', environments: ['cli', 'mcp'],
        parameters: [{ name: 'limit', type: 'number' }, { name: 'active', type: 'confirm' }] }] },
  };
  assert.doesNotThrow(() => validate(PluginSchema, plugin));
  assert.throws(() => validate(PluginSchema, { ...plugin, packageName: '' }), ValidationError);
  const command = createMCPDevToolsExtensionSchema(plugin, z);
  assert.equal(command.safeParse({ command: 'inspect', limit: 3, active: true }).success, true);
  for (const input of [{ command: 'unknown' }, { command: 'inspect', limit: '3' },
    { command: 'inspect', extra: true }]) {
    assert.equal(command.safeParse(input).success, false);
  }
  assert.doesNotThrow(() => validate(DevToolsPluginOutputSchema, [
    { type: 'text', text: 'ok', level: 'info' },
    { type: 'image', url: 'https://example.invalid/image.png' }]));
  assert.throws(() => validate(DevToolsPluginOutputSchema, [
    { type: 'audio', url: 'not a URL' }]), ValidationError);
});

test('Expo fingerprint path matching remains compatible with minimatch 11', () => {
  const fingerprintRoot = dirname(expoRequire.resolve('@expo/fingerprint/package.json'));
  const fingerprintRequire = createRequire(join(fingerprintRoot, 'package.json'));
  assert.equal(fingerprintRequire.resolve('minimatch'), require.resolve('minimatch'));
  const { isIgnoredPath, buildPathMatchObjects, buildDirMatchObjects } = require(join(
    fingerprintRoot, 'build/utils/Path.js'));
  assert.equal(isIgnoredPath('node_modules/example/index.js', ['node_modules/**']), true);
  assert.equal(isIgnoredPath('src/auth.ts', ['node_modules/**']), false);
  assert.equal(buildPathMatchObjects(['**/*.ts'])[0].match('src/auth.ts'), true);
  assert.ok(Array.isArray(buildDirMatchObjects(buildPathMatchObjects(['assets/**']))));
});

test('forge signing verifies valid content but rejects changed content', () => {
  const forge = require('node-forge');
  const keys = forge.pki.rsa.generateKeyPair(1024);
  const md = forge.md.sha256.create().update('synthetic-build-compatibility');
  const signature = keys.privateKey.sign(md);
  assert.equal(keys.publicKey.verify(md.digest().bytes(), signature), true);
  const changed = forge.md.sha256.create().update('changed');
  assert.equal(keys.publicKey.verify(changed.digest().bytes(), signature), false);
});

test('the actual Expo tunnel consumer uses the patched CommonJS UUID API', async () => {
  const ngrokEntry = require.resolve('@expo/ngrok');
  const ngrokRequire = createRequire(ngrokEntry);
  const uuid = ngrokRequire('uuid');
  assert.equal(ngrokRequire('uuid/package.json').version, '11.1.1');
  assert.equal(typeof require('@expo/ngrok').connect, 'function');
  assert.equal(uuid.validate(uuid.v4()), true);

  const requests = [];
  const processes = [];
  let attempts = 0;
  class OfflineClient {
    constructor(url) { assert.equal(url, 'http://127.0.0.1:4040'); }
    async startTunnel(options) {
      requests.push({ ...options });
      if (attempts++ === 0) {
        throw { response: { statusCode: 502 },
          body: { details: { err: 'tunnel session not ready yet' } } };
      }
      return { public_url: 'https://synthetic-tunnel.example.invalid' };
    }
  }
  const isolated = { exports: {} };
  // Execute the installed consumer itself; stub only I/O. No tunnel is opened,
  // no agent binary starts and no local ngrok config or credential is read.
  runInNewContext(readFileSync(ngrokEntry, 'utf8'), {
    module: isolated,
    require(id) {
      if (id === './src/client') return { NgrokClient: OfflineClient };
      if (id === './src/process') return {
        getProcess: async options => {
          processes.push({ ...options });
          return 'http://127.0.0.1:4040';
        },
        setAuthtoken: async () => { throw new Error('Unexpected credential use'); },
      };
      return ngrokRequire(id);
    },
    setTimeout,
  }, { filename: ngrokEntry });
  const result = await isolated.exports.connect({ addr: 8081, proto: 'http' });
  assert.equal(result, 'https://synthetic-tunnel.example.invalid');
  assert.equal(processes.length, 1);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].name, requests[1].name);
  assert.equal(uuid.validate(requests[0].name), true);
  assert.equal(uuid.version(requests[0].name), 4);
  assert.equal(requests[0].addr, 8081);
});

test('patched tunnel UUID rejects out-of-bounds v3/v5/v6 writes without partial data', () => {
  const ngrokRequire = createRequire(require.resolve('@expo/ngrok'));
  const uuid = ngrokRequire('uuid');
  for (const offset of [-1, 0, 4]) {
    for (const generate of [
      buffer => uuid.v3('synthetic', uuid.v3.DNS, buffer, offset),
      buffer => uuid.v5('synthetic', uuid.v5.DNS, buffer, offset),
      buffer => uuid.v6({}, buffer, offset),
    ]) {
      const buffer = new Uint8Array(8).fill(0xaa);
      assert.throws(() => generate(buffer), RangeError);
      assert.deepEqual(buffer, new Uint8Array(8).fill(0xaa));
    }
  }
});
