import assert from 'node:assert/strict';
import test from 'node:test';

import { captureAndScanIdentity } from '../checkinCapture.js';

test('accepted camera photo is sent to the identity parser', async () => {
  const scanned: string[] = [];
  const result = await captureAndScanIdentity({
    launchCamera: async () => ({ canceled: false, assets: [{ uri: 'file:///id.jpg' }] }),
    scanPhoto: async (uri) => {
      scanned.push(uri);
      return { first_name: 'Ada' };
    },
  });

  assert.deepEqual(scanned, ['file:///id.jpg']);
  assert.deepEqual(result, { status: 'parsed', data: { first_name: 'Ada' } });
});

test('camera cancellation returns to the caller without scanning', async () => {
  let scanCalls = 0;
  const result = await captureAndScanIdentity({
    launchCamera: async () => ({ canceled: true }),
    scanPhoto: async () => {
      scanCalls += 1;
      return {};
    },
  });

  assert.equal(scanCalls, 0);
  assert.deepEqual(result, { status: 'cancelled' });
});

test('missing camera asset becomes a recoverable failure', async () => {
  const result = await captureAndScanIdentity({
    launchCamera: async () => ({ canceled: false, assets: [] }),
    scanPhoto: async () => ({}),
  });

  assert.equal(result.status, 'failed');
  if (result.status === 'failed') {
    assert.match(String(result.error), /fotoğrafı alınamadı/i);
  }
});
