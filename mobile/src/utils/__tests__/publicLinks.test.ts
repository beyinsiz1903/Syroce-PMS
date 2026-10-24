import assert from 'node:assert/strict';
import test from 'node:test';
import { PUBLIC_LINKS } from '../publicLinks.js';

test('privacy and support use fixed public HTTPS pages without credentials or query data', () => {
  assert.equal(PUBLIC_LINKS.privacy, 'https://pms.syroce.com/privacy-policy');
  assert.equal(PUBLIC_LINKS.support, 'https://pms.syroce.com/otel-programi');
  for (const link of Object.values(PUBLIC_LINKS)) {
    const url = new URL(link);
    assert.equal(url.protocol, 'https:');
    assert.equal(url.origin, 'https://pms.syroce.com');
    assert.equal(url.username + url.password + url.search + url.hash, '');
  }
});
