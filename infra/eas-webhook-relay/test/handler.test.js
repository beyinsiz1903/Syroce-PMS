'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

const {
  handleWebhook,
  verifyExpoSignature,
  buildClientPayload,
  extractIssueNumber,
  loadConfigFromEnv,
  RelayError,
} = require('../src/handler');

const SECRET = 'super-secret-test-value';

function sign(body, secret = SECRET) {
  const hex = crypto.createHmac('sha1', secret).update(body).digest('hex');
  return `sha1=${hex}`;
}

function makePayload(overrides = {}) {
  return JSON.stringify({
    id: 'build-123',
    status: 'finished',
    platform: 'ios',
    artifacts: {
      buildUrl: 'https://expo.dev/artifacts/build-123',
      applicationArchiveUrl: 'https://expo.dev/artifacts/eas/build-123.tar.gz',
    },
    metadata: {
      buildProfile: 'preview',
      gitCommitMessage: 'feat: ship things',
      gitBranch: 'main',
    },
    ...overrides,
  });
}

function makeConfig(overrides = {}) {
  return {
    easWebhookSecret: SECRET,
    githubRepo: 'syroce/pms',
    githubToken: 'ghp_test',
    defaultProfile: 'preview',
    userAgent: 'eas-webhook-relay-test',
    ...overrides,
  };
}

function makeFetchSpy({ status = 204 } = {}) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      status,
      async text() {
        return status === 204 ? '' : 'github error body';
      },
    };
  };
  return { fetchImpl, calls };
}

test('verifyExpoSignature accepts a valid sha1 hex signature', () => {
  const body = Buffer.from('{"hello":"world"}', 'utf8');
  const header = sign(body);
  assert.doesNotThrow(() => verifyExpoSignature({
    rawBody: body, signatureHeader: header, secret: SECRET,
  }));
});

test('verifyExpoSignature rejects a tampered signature', () => {
  const body = Buffer.from('{"hello":"world"}', 'utf8');
  const header = sign(body, 'other-secret');
  assert.throws(
    () => verifyExpoSignature({ rawBody: body, signatureHeader: header, secret: SECRET }),
    (err) => err instanceof RelayError && err.status === 401,
  );
});

test('verifyExpoSignature rejects malformed header', () => {
  const body = Buffer.from('{}', 'utf8');
  for (const bad of ['', 'sha256=abc', 'plainstring', 'sha1=zzz']) {
    assert.throws(
      () => verifyExpoSignature({ rawBody: body, signatureHeader: bad, secret: SECRET }),
      (err) => err instanceof RelayError && err.status === 401,
      `expected 401 for header '${bad}'`,
    );
  }
});

test('extractIssueNumber finds PR number in commit message', () => {
  assert.equal(extractIssueNumber({ metadata: { gitCommitMessage: 'fix: PR-42' } }), '42');
  assert.equal(extractIssueNumber({ metadata: { gitCommitMessage: 'closes #137' } }), '137');
  assert.equal(extractIssueNumber({ metadata: { gitBranch: 'pr-99/foo' } }), '99');
  assert.equal(extractIssueNumber({ metadata: { gitCommitMessage: 'no number here' } }), '');
  assert.equal(extractIssueNumber({}), '');
});

test('buildClientPayload returns the expected shape', () => {
  const payload = JSON.parse(makePayload());
  const result = buildClientPayload(payload, { defaultProfile: 'preview' });
  assert.deepEqual(result, {
    platform: 'ios',
    build_url: 'https://expo.dev/artifacts/eas/build-123.tar.gz',
    build_id: 'build-123',
    profile: 'preview',
  });
});

test('buildClientPayload includes issue_number when discoverable', () => {
  const payload = JSON.parse(makePayload({
    metadata: {
      buildProfile: 'production',
      gitCommitMessage: 'release: closes #321',
      gitBranch: 'release/2.4',
    },
  }));
  const result = buildClientPayload(payload, { defaultProfile: 'preview' });
  assert.equal(result.profile, 'production');
  assert.equal(result.issue_number, '321');
});

test('buildClientPayload rejects unsupported platform', () => {
  const payload = JSON.parse(makePayload({ platform: 'web' }));
  assert.throws(
    () => buildClientPayload(payload, { defaultProfile: 'preview' }),
    (err) => err instanceof RelayError && err.status === 400,
  );
});

test('buildClientPayload rejects missing artifact URL', () => {
  const payload = JSON.parse(makePayload({ artifacts: {} }));
  assert.throws(
    () => buildClientPayload(payload, { defaultProfile: 'preview' }),
    (err) => err instanceof RelayError && err.status === 400,
  );
});

test('handleWebhook dispatches when status=finished', async () => {
  const body = makePayload();
  const headers = { 'expo-signature': sign(body) };
  const { fetchImpl, calls } = makeFetchSpy();

  const silentLogger = { info() {} };
  const result = await handleWebhook({
    rawBody: body,
    headers,
    config: makeConfig(),
    fetchImpl,
    logger: silentLogger,
  });

  assert.equal(result.dispatched, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.github.com/repos/syroce/pms/dispatches');
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer ghp_test');
  assert.equal(calls[0].init.headers.Accept, 'application/vnd.github+json');
  assert.equal(calls[0].init.headers['X-GitHub-Api-Version'], '2022-11-28');

  const sentBody = JSON.parse(calls[0].init.body);
  assert.equal(sentBody.event_type, 'eas-build-finished');
  assert.deepEqual(sentBody.client_payload, {
    platform: 'ios',
    build_url: 'https://expo.dev/artifacts/eas/build-123.tar.gz',
    build_id: 'build-123',
    profile: 'preview',
  });
});

test('handleWebhook swallows non-finished status without dispatching', async () => {
  const body = makePayload({ status: 'in-queue' });
  const headers = { 'expo-signature': sign(body) };
  const { fetchImpl, calls } = makeFetchSpy();

  const silentLogger = { info() {} };
  const result = await handleWebhook({
    rawBody: body,
    headers,
    config: makeConfig(),
    fetchImpl,
    logger: silentLogger,
  });

  assert.equal(result.dispatched, false);
  assert.equal(result.status, 'in-queue');
  assert.equal(calls.length, 0);
});

test('handleWebhook also swallows status=errored', async () => {
  const body = makePayload({ status: 'errored' });
  const headers = { 'expo-signature': sign(body) };
  const { fetchImpl, calls } = makeFetchSpy();

  const silentLogger = { info() {} };
  const result = await handleWebhook({
    rawBody: body, headers, config: makeConfig(), fetchImpl, logger: silentLogger,
  });
  assert.equal(result.dispatched, false);
  assert.equal(calls.length, 0);
});

test('handleWebhook rejects bad HMAC with 401', async () => {
  const body = makePayload();
  const headers = { 'expo-signature': sign(body, 'wrong-secret') };
  const { fetchImpl, calls } = makeFetchSpy();
  await assert.rejects(
    handleWebhook({ rawBody: body, headers, config: makeConfig(), fetchImpl, logger: { info() {} } }),
    (err) => err instanceof RelayError && err.status === 401,
  );
  assert.equal(calls.length, 0);
});

test('handleWebhook rejects when config is incomplete', async () => {
  const body = makePayload();
  const headers = { 'expo-signature': sign(body) };
  await assert.rejects(
    handleWebhook({
      rawBody: body,
      headers,
      config: makeConfig({ githubToken: '' }),
      fetchImpl: makeFetchSpy().fetchImpl,
      logger: { info() {} },
    }),
    (err) => err instanceof RelayError && err.status === 500,
  );
});

test('handleWebhook surfaces GitHub API failures as 502', async () => {
  const body = makePayload();
  const headers = { 'expo-signature': sign(body) };
  const { fetchImpl } = makeFetchSpy({ status: 422 });
  await assert.rejects(
    handleWebhook({ rawBody: body, headers, config: makeConfig(), fetchImpl, logger: { info() {} } }),
    (err) => err instanceof RelayError && err.status === 502,
  );
});

test('handleWebhook accepts case-insensitive headers (lambda-style)', async () => {
  const body = makePayload();
  const headers = { 'Expo-Signature': sign(body) };
  const { fetchImpl, calls } = makeFetchSpy();
  const result = await handleWebhook({
    rawBody: body, headers, config: makeConfig(), fetchImpl, logger: { info() {} },
  });
  assert.equal(result.dispatched, true);
  assert.equal(calls.length, 1);
});

test('loadConfigFromEnv reads expected variables', () => {
  const cfg = loadConfigFromEnv({
    EAS_WEBHOOK_SECRET: 's',
    GITHUB_REPO: 'a/b',
    GITHUB_TOKEN: 't',
    GITHUB_DEFAULT_PROFILE: 'production',
  });
  assert.equal(cfg.easWebhookSecret, 's');
  assert.equal(cfg.githubRepo, 'a/b');
  assert.equal(cfg.githubToken, 't');
  assert.equal(cfg.defaultProfile, 'production');
});
