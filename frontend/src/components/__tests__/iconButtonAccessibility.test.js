import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = (name) => readFileSync(resolve(process.cwd(), `src/components/${name}`), 'utf8');

describe('shared icon buttons', () => {
  it('exposes names for launcher, notification and photo actions', () => {
    expect(source('AppLauncher.jsx')).toContain('aria-label="Çalışma alanlarını aç"');
    expect(source('NotificationCenter.jsx')).toContain('aria-label="Tüm bildirimleri temizle"');
    expect(source('NotificationCenter.jsx')).toContain('aria-label="Bildirim merkezini kapat"');
    expect(source('PhotoUploadComponent.jsx')).toContain('aria-label="Seçilen fotoğrafı kaldır"');
  });

  it('labels the housekeeping refresh action', () => {
    expect(source('HousekeepingQualityPanel.jsx')).toContain('aria-label="Kalite kontrol verilerini yenile"');
  });
});
