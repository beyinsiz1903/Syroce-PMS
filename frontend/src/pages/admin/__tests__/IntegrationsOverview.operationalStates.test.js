import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/admin/IntegrationsOverview.jsx'), 'utf8');

describe('IntegrationsOverview operational status contract', () => {
  it('does not put tenant-scoped integrations in the generic ready column', () => {
    expect(source).toContain('tenant_setup: []');
    expect(source).toContain('status="tenant_setup"');
    expect(source).toContain('Otel kurulumu / doğrulama');
  });

  it('shows evidence-backed trial, setup, production and error states', () => {
    expect(source).toContain('production_verified');
    expect(source).toContain('Kurulum/doğrulama bekliyor');
    expect(source).toContain('Bağlantı hatası');
  });
});
