'use strict';

const http = require('http');
const { handleWebhook, loadConfigFromEnv, RelayError } = require('./handler');

const WEBHOOK_PATH = process.env.WEBHOOK_PATH || '/eas';
const PORT = Number.parseInt(process.env.PORT || '8080', 10);
const MAX_BODY_BYTES = Number.parseInt(process.env.MAX_BODY_BYTES || '1048576', 10);

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new RelayError(413, `request body exceeds ${MAX_BODY_BYTES} bytes`));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
  });
  res.end(payload);
}

async function requestHandler(req, res) {
  if (req.method === 'GET' && (req.url === '/health' || req.url === '/healthz')) {
    sendJson(res, 200, { ok: true });
    return;
  }
  if (req.method !== 'POST' || req.url !== WEBHOOK_PATH) {
    sendJson(res, 404, { error: 'not found' });
    return;
  }

  let rawBody;
  try {
    rawBody = await readBody(req);
  } catch (err) {
    const status = err instanceof RelayError ? err.status : 400;
    sendJson(res, status, { error: err.message || 'invalid body' });
    return;
  }

  try {
    const result = await handleWebhook({
      rawBody,
      headers: req.headers,
      config: loadConfigFromEnv(),
    });
    sendJson(res, result.dispatched ? 202 : 200, {
      ok: true,
      dispatched: result.dispatched,
      status: result.status || null,
      reason: result.reason || null,
    });
  } catch (err) {
    const status = err instanceof RelayError ? err.status : 500;
    if (status >= 500) {
      console.error('[eas-relay] error', err.message, err.logExtra || '');
    } else {
      console.warn('[eas-relay] rejected', err.message);
    }
    sendJson(res, status, { error: err.message || 'internal error' });
  }
}

function start({ port = PORT } = {}) {
  const server = http.createServer(requestHandler);
  server.listen(port, '0.0.0.0', () => {
    console.log(`[eas-relay] listening on 0.0.0.0:${port} (webhook path: ${WEBHOOK_PATH})`);
  });
  const shutdown = (signal) => {
    console.log(`[eas-relay] received ${signal}, shutting down`);
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 10_000).unref();
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
  return server;
}

if (require.main === module) {
  start();
}

module.exports = { start, requestHandler };
