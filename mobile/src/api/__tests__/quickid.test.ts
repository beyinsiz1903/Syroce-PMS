import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeQuickIdResponse } from '../../utils/quickidResponse.js';

test('normalizes the current embedded Quick-ID documents response', () => {
  assert.deepEqual(
    normalizeQuickIdResponse({
      success: true,
      documents: [
        {
          first_name: 'Ayşe',
          last_name: 'Yılmaz',
          id_number: '12345678901',
          document_type: 'tc_kimlik',
          nationality: 'TR',
          birth_date: '1990-05-15',
        },
      ],
    }),
    {
      first_name: 'Ayşe',
      last_name: 'Yılmaz',
      full_name: 'Ayşe Yılmaz',
      id_number: '12345678901',
      passport_number: undefined,
      nationality: 'TR',
      birth_date: '1990-05-15',
      document_type: 'tc_kimlik',
    },
  );
});

test('maps a passport document number without treating it as a Turkish ID', () => {
  const result = normalizeQuickIdResponse({
    extracted_data: {
      documents: [
        {
          first_name: 'Ada',
          last_name: 'Lovelace',
          document_number: 'P123456',
          document_type: 'passport',
        },
      ],
    },
  });

  assert.equal(result.passport_number, 'P123456');
  assert.equal(result.id_number, undefined);
});

test('rejects an empty OCR result with actionable guidance', () => {
  assert.throws(
    () => normalizeQuickIdResponse({ success: true, documents: [] }),
    /okunabilir bilgi bulunamadı/i,
  );
});
