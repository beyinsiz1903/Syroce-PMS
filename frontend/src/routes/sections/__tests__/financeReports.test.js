import { describe, expect, it, vi } from 'vitest';
import { financeReportsRoutes } from '../financeReports';

const p = vi.fn((component) => ({ type: 'protected', component }));

describe('financeReportsRoutes', () => {
  it('keeps a single canonical workspace URL for settings and report aliases', () => {
    const routes = financeReportsRoutes({ p });
    const byPath = Object.fromEntries(routes.map((route) => [route.path, route]));

    expect(byPath['/app/raporlar'].type).toBe('protected');
    expect(byPath['/reports']).toMatchObject({ type: 'redirect', to: '/app/raporlar', preserveLocation: true });
    expect(byPath['/app/reports']).toMatchObject({ type: 'redirect', to: '/app/raporlar', preserveLocation: true });
    expect(byPath['/app/gelismis-raporlar']).toMatchObject({ type: 'redirect', to: '/app/raporlar', preserveLocation: true });
    expect(byPath['/settings']).toMatchObject({ type: 'redirect', to: '/app/settings', preserveLocation: true });
  });

  it('directs the report builder alias to its canonical route', () => {
    const routes = financeReportsRoutes({ p });
    const alias = routes.find((route) => route.path === '/app/rapor-olusturucu');
    expect(alias).toMatchObject({ type: 'redirect', to: '/reports/builder', preserveLocation: true });
  });
});
