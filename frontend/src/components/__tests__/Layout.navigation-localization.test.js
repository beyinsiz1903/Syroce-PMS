import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const layoutSource = readFileSync(resolve(process.cwd(), 'src/components/Layout.jsx'), 'utf8');
const tr = JSON.parse(readFileSync(resolve(process.cwd(), 'src/locales/tr.json'), 'utf8'));
const en = JSON.parse(readFileSync(resolve(process.cwd(), 'src/locales/en.json'), 'utf8'));

describe('top navigation localization', () => {
  it('places desktop navigation above the workspace without a fixed-width rail', () => {
    expect(layoutSource).toContain('data-testid="desktop-top-navigation"');
    expect(layoutSource).toContain('hidden xl:flex w-full shrink-0 flex-wrap');
    expect(layoutSource).not.toContain('hidden xl:flex w-64');
    expect(layoutSource).toContain('xl:hidden absolute inset-x-0 top-full');
    expect(layoutSource).toContain('WorkspaceTools key={scope}');
  });
  it('uses native labels for the primary navigation in Turkish and English', () => {
    expect(tr.navKeys.dashboard).toBe('Kontrol Paneli');
    expect(en.navKeys.dashboard).toBe('Dashboard');
    expect(tr.navKeys.rooms).toBe('Odalar');
    expect(en.navKeys.rooms).toBe('Rooms');
    expect(tr.navKeys.reservation_calendar).toBe('Takvim');
    expect(en.navKeys.reservation_calendar).toBe('Calendar');
  });

  it('localizes role-specific workspace labels instead of hard-coding Turkish', () => {
    expect(layoutSource).toContain("t('navKeys.accounting', 'Muhasebe')");
    expect(layoutSource).toContain("t('navKeys.general_manager_dashboard', 'GM Paneli')");
    expect(en.navKeys.accounting).toBe('Accounting');
    expect(en.navKeys.general_manager_dashboard).toBe('GM Dashboard');
  });

  it('uses the locale dictionary for the rooms shortcut', () => {
    expect(layoutSource).toContain("const roomsLabel = t('navKeys.rooms', 'Odalar')");
    expect(layoutSource).toContain('aria-label={roomsLabel}');
    expect(layoutSource).not.toContain('aria-label="Odalar"');
  });

  it('keeps the paid module marketplace permanently discoverable', () => {
    expect(layoutSource).toContain('data-testid="nav-module-store-shortcut"');
    expect(layoutSource).toContain('data-testid="mobile-nav-module-store"');
    expect(layoutSource).toContain("handleNavigate('/app/module-store')");
    expect(layoutSource).toContain("t('navKeys.module_store', 'Modül Pazarı')");
  });
});
