import assert from 'node:assert/strict';
import test from 'node:test';

import { quickIdErrorMessage } from '../quickidErrors.js';

test('gives photo quality guidance for unreadable OCR output', () => {
  const message = quickIdErrorMessage({ status: 422, message: 'Görüntüde okunabilir kimlik metni bulunamadı' });
  assert.match(message, /dört köşe/i);
  assert.match(message, /yansıması/i);
});

test('distinguishes service outage, timeout and connectivity failures', () => {
  assert.match(quickIdErrorMessage({ status: 503, message: 'OCR sağlayıcısı kullanılamıyor' }), /hazır değil/i);
  assert.match(quickIdErrorMessage({ status: 504, message: 'timeout' }), /zaman aşımına/i);
  assert.match(quickIdErrorMessage({ status: 0, message: 'NETWORK' }), /bağlantısını/i);
});

test('does not expose an unknown technical exception', () => {
  const message = quickIdErrorMessage(new TypeError("Cannot read property 'slice' of null"));
  assert.doesNotMatch(message, /TypeError|slice/i);
  assert.match(message, /yeniden çekin/i);
});
