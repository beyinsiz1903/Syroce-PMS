'use strict';

const crypto = require('crypto');

const EAS_SIGNATURE_HEADER = 'expo-signature';
const DISPATCH_EVENT_TYPE = 'eas-build-finished';

class RelayError extends Error {
  constructor(status, message, { logExtra } = {}) {
    super(message);
    this.status = status;
    this.logExtra = logExtra;
  }
}

function timingSafeEqualHex(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  if (a.length !== b.length) return false;
  let bufA;
  let bufB;
  try {
    bufA = Buffer.from(a, 'hex');
    bufB = Buffer.from(b, 'hex');
  } catch (_err) {
    return false;
  }
  if (bufA.length === 0 || bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

function verifyExpoSignature({ rawBody, signatureHeader, secret }) {
  if (!signatureHeader || typeof signatureHeader !== 'string') {
    throw new RelayError(401, 'missing expo-signature header');
  }
  if (!secret) {
    throw new RelayError(500, 'EAS_WEBHOOK_SECRET is not configured');
  }
  const match = /^sha1=([0-9a-f]+)$/i.exec(signatureHeader.trim());
  if (!match) {
    throw new RelayError(401, 'expo-signature header is not a sha1=<hex> value');
  }
  const provided = match[1].toLowerCase();
  const expected = crypto.createHmac('sha1', secret).update(rawBody).digest('hex');
  if (!timingSafeEqualHex(provided, expected)) {
    throw new RelayError(401, 'expo-signature does not match HMAC-SHA1 of body');
  }
}

function parseJson(rawBody) {
  let text;
  if (Buffer.isBuffer(rawBody)) {
    text = rawBody.toString('utf8');
  } else if (typeof rawBody === 'string') {
    text = rawBody;
  } else {
    throw new RelayError(400, 'request body must be a buffer or string');
  }
  if (!text.trim()) {
    throw new RelayError(400, 'request body is empty');
  }
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new RelayError(400, `request body is not valid JSON: ${err.message}`);
  }
}

function extractIssueNumber(payload) {
  const meta = payload && payload.metadata;
  if (!meta) return '';
  const candidates = [
    meta.gitCommitMessage,
    meta.message,
    meta.gitBranch,
  ].filter((v) => typeof v === 'string' && v.length > 0);
  for (const candidate of candidates) {
    const m = /(?:^|[^0-9])(?:pr|issue|#)[ -]?(\d{1,6})\b/i.exec(candidate);
    if (m) return m[1];
  }
  return '';
}

function buildClientPayload(payload, { defaultProfile }) {
  const platform = payload.platform;
  if (platform !== 'ios' && platform !== 'android') {
    throw new RelayError(400, `unsupported platform '${platform}' (expected 'ios' or 'android')`);
  }
  const artifacts = payload.artifacts || {};
  const buildUrl = artifacts.applicationArchiveUrl || artifacts.buildUrl;
  if (!buildUrl || typeof buildUrl !== 'string') {
    throw new RelayError(400, 'payload.artifacts.applicationArchiveUrl is missing');
  }
  const buildId = payload.id;
  if (!buildId || typeof buildId !== 'string') {
    throw new RelayError(400, 'payload.id is missing');
  }
  const meta = payload.metadata || {};
  const profile = (typeof meta.buildProfile === 'string' && meta.buildProfile)
    || (typeof payload.profile === 'string' && payload.profile)
    || defaultProfile
    || 'preview';
  const out = {
    platform,
    build_url: buildUrl,
    build_id: buildId,
    profile,
  };
  const issueNumber = extractIssueNumber(payload);
  if (issueNumber) out.issue_number = issueNumber;
  return out;
}

async function dispatchToGithub({ repo, token, clientPayload, fetchImpl, userAgent }) {
  const fetchFn = fetchImpl || globalThis.fetch;
  if (typeof fetchFn !== 'function') {
    throw new RelayError(500, 'fetch is not available in this runtime');
  }
  const url = `https://api.github.com/repos/${repo}/dispatches`;
  const res = await fetchFn(url, {
    method: 'POST',
    headers: {
      'Accept': 'application/vnd.github+json',
      'Authorization': `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': userAgent || 'eas-webhook-relay',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      event_type: DISPATCH_EVENT_TYPE,
      client_payload: clientPayload,
    }),
  });
  if (res.status === 204) return;
  let body = '';
  try {
    body = await res.text();
  } catch (_err) {
    body = '<unreadable>';
  }
  throw new RelayError(
    502,
    `GitHub dispatch failed: HTTP ${res.status}`,
    { logExtra: { githubStatus: res.status, githubBody: body.slice(0, 500) } },
  );
}

async function handleWebhook({
  rawBody,
  headers,
  config,
  fetchImpl,
  logger = console,
} = {}) {
  if (!config || typeof config !== 'object') {
    throw new RelayError(500, 'relay config is missing');
  }
  const requiredKeys = ['easWebhookSecret', 'githubRepo', 'githubToken'];
  for (const key of requiredKeys) {
    if (!config[key]) {
      throw new RelayError(500, `relay config is missing '${key}'`);
    }
  }
  if (!/^[^/\s]+\/[^/\s]+$/.test(config.githubRepo)) {
    throw new RelayError(500, "githubRepo must be in 'owner/repo' format");
  }

  const lcHeaders = {};
  for (const [k, v] of Object.entries(headers || {})) {
    lcHeaders[k.toLowerCase()] = Array.isArray(v) ? v[0] : v;
  }

  verifyExpoSignature({
    rawBody,
    signatureHeader: lcHeaders[EAS_SIGNATURE_HEADER],
    secret: config.easWebhookSecret,
  });

  const payload = parseJson(rawBody);
  const status = payload && payload.status;

  if (status !== 'finished') {
    logger.info && logger.info('[eas-relay] swallowing non-finished webhook', {
      status,
      buildId: payload && payload.id,
      platform: payload && payload.platform,
    });
    return { dispatched: false, status, reason: 'status-not-finished' };
  }

  const clientPayload = buildClientPayload(payload, {
    defaultProfile: config.defaultProfile,
  });

  await dispatchToGithub({
    repo: config.githubRepo,
    token: config.githubToken,
    clientPayload,
    fetchImpl,
    userAgent: config.userAgent,
  });

  logger.info && logger.info('[eas-relay] dispatched eas-build-finished', {
    buildId: clientPayload.build_id,
    platform: clientPayload.platform,
    profile: clientPayload.profile,
    issueNumber: clientPayload.issue_number || null,
  });

  return { dispatched: true, status, clientPayload };
}

function loadConfigFromEnv(env = process.env) {
  return {
    easWebhookSecret: env.EAS_WEBHOOK_SECRET || '',
    githubRepo: env.GITHUB_REPO || '',
    githubToken: env.GITHUB_TOKEN || '',
    defaultProfile: env.GITHUB_DEFAULT_PROFILE || 'preview',
    userAgent: env.RELAY_USER_AGENT || 'eas-webhook-relay',
  };
}

module.exports = {
  RelayError,
  verifyExpoSignature,
  buildClientPayload,
  extractIssueNumber,
  dispatchToGithub,
  handleWebhook,
  loadConfigFromEnv,
  DISPATCH_EVENT_TYPE,
  EAS_SIGNATURE_HEADER,
};
