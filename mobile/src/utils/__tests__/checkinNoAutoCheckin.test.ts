import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const source = readFileSync(resolve(process.cwd(), 'app/(frontdesk)/checkin.tsx'), 'utf8');

test('quick identity flow cannot invoke check-in or walk-in automatically', () => {
  assert.doesNotMatch(source, /\bcheckin\s*\(/);
  assert.doesNotMatch(source, /\bwalkInQuick\b/);
  assert.doesNotMatch(source, /\/api\/frontdesk\/checkin/);
  assert.match(source, /addReservationGuest\s*\(/);
  assert.match(source, /ROUTES\.newReservation/);
});

