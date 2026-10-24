import assert from 'node:assert/strict';
import test from 'node:test';
import { userSafeErrorMessage } from '../userSafeErrorMessage.js';

const fallback = 'Rezervasyon hesabı yüklenemedi. Lütfen tekrar deneyin.';

test('raw HTTP and transport failures use a contextual message, not missing-account claims', () => {
  for (const value of ['Not Found', '  Not Found  ', 'Forbidden', 'Unauthorized', 'Internal Server Error', 'Bad Gateway', 'Service Unavailable', 'request_failed', 'NETWORK', 'Failed to fetch', 'Network request failed', '', undefined]) {
    assert.equal(userSafeErrorMessage(value, fallback), fallback);
  }
});

test('specific missing-resource and permission messages remain distinct', () => {
  for (const value of ['Rezervasyon bulunamadı', 'Bu işlem için yetkiniz yok', 'Çıkış için önce açık bakiyeyi kapatın']) {
    assert.equal(userSafeErrorMessage(value, fallback), value);
  }
});

test('native paths and stack traces stay out of the user interface', () => {
  for (const value of ['TypeError: undefined is not an object', '/var/mobile/Containers/Data/secret', 'main.bundle:140', 'Error\n    at request (client.ts:13)']) {
    assert.equal(userSafeErrorMessage(value, fallback), fallback);
  }
});

test('internal subscription module keys are replaced with actionable copy', () => {
  assert.equal(userSafeErrorMessage('Planınıza dahil değil: revenue_management', fallback), 'Bu özellik otelinizin paketinde etkin değil.');
});
