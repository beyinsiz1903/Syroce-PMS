import test from 'node:test';
import assert from 'node:assert/strict';
import { demoPreviewEnabled } from '../previewMode';

test('demo preview is explicit and loopback-only', () => {
  assert.equal(demoPreviewEnabled(true, 'demo', 'http://127.0.0.1:18999'), true);
  assert.equal(demoPreviewEnabled(true, 'demo', 'http://localhost:18999/'), true);
  for (const url of [undefined, 'https://pms.syroce.com', 'http://localhost:8000', 'http://localhost:18999.evil.invalid', 'http://192.168.1.2:18999']) {
    assert.equal(demoPreviewEnabled(true, 'demo', url), false);
  }
  assert.equal(demoPreviewEnabled(false, 'demo', 'http://127.0.0.1:18999'), false);
  assert.equal(demoPreviewEnabled(true, undefined, 'http://127.0.0.1:18999'), false);
});
