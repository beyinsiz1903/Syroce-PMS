import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';

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

test('Expo devtools accepts valid schemas and rejects invalid input with Zod 4', () => {
  const { PluginSchema, DevToolsPluginOutputSchema } = require(join(cliRoot,
    'build/src/start/server/DevToolsPlugin.schema.js'));
  const { createMCPDevToolsExtensionSchema } = require(join(cliRoot,
    'build/src/start/server/createMCPDevToolsExtensionSchema.js'));
  const plugin = {
    packageName: 'synthetic-devtool', packageRoot: '/synthetic',
    cliExtensions: { description: 'local compatibility check', entryPoint: 'index.js',
      commands: [{ name: 'inspect', title: 'Inspect', environments: ['cli', 'mcp'],
        parameters: [{ name: 'limit', type: 'number' }, { name: 'active', type: 'confirm' }] }] },
  };
  assert.equal(PluginSchema.safeParse(plugin).success, true);
  assert.equal(PluginSchema.safeParse({ ...plugin, packageName: '' }).success, false);
  const command = createMCPDevToolsExtensionSchema(plugin);
  assert.equal(command.safeParse({ command: 'inspect', limit: 3, active: true }).success, true);
  for (const input of [{ command: 'unknown' }, { command: 'inspect', limit: '3' },
    { command: 'inspect', extra: true }]) {
    assert.equal(command.safeParse(input).success, false);
  }
  assert.equal(DevToolsPluginOutputSchema.safeParse([
    { type: 'text', text: 'ok', level: 'info' },
    { type: 'image', url: 'https://example.invalid/image.png' }]).success, true);
  assert.equal(DevToolsPluginOutputSchema.safeParse([
    { type: 'audio', url: 'not a URL' }]).success, false);
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
