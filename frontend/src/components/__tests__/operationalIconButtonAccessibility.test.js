import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const read = (path) => readFileSync(resolve(process.cwd(), `src/components/${path}`), 'utf8');

describe('operational icon actions', () => {
  it('names destructive folio and messaging actions for assistive technology', () => {
    expect(read('SplitFolioDialog.jsx')).toContain('folyo bölme hedefini kaldır');
    expect(read('pms/InternalChatTab.jsx')).toContain('Tüm okunmamış mesajları okundu olarak işaretle');
    expect(read('pms/InternalChatTab.jsx')).toContain('Mesaj kutusunu yenile');
  });

  it('names guest-request navigation, refresh and send actions', () => {
    const source = read('pms/internalChat/GuestRequestsPanel.jsx');
    expect(source).toContain('Misafir talepleri listesine dön');
    expect(source).toContain('Misafir talebi konuşmasını yenile');
    expect(source).toContain('Misafir talebine yanıt gönder');
    expect(source).toContain('Misafir talepleri listesini yenile');
  });
});
