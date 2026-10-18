import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ModuleSetupList, { isReadinessMap, splitReadiness } from '../ModuleSetupList';

const modules = {
  spa: { module: 'spa', status: 'incomplete', setup: [
    { key: 'spa_services', label: 'SPA hizmeti', ok: true, path: '/spa-wellness' },
    { key: 'spa_therapists', label: 'Terapist', ok: false, path: '/spa-wellness' },
  ], usage: [] },
  pms: { module: 'pms', status: 'incomplete', setup: [{ key: 'rooms', label: 'Odalar tanımlı', ok: false, path: '/app/onboarding' }], usage: [] },
  mice: { module: 'mice', status: 'idle', setup: [], usage: [{ label: 'Son 30 günde etkinlik / fırsat', ok: false }] },
  housekeeping: { module: 'housekeeping', status: 'active', setup: [], usage: [] },
  hr: { module: 'hr', status: 'off', setup: [], usage: [] },
};

describe('ModuleSetupList', () => {
  it('splits by setup state and leaves off modules out', () => {
    const split = splitReadiness(modules);
    expect(split.incomplete.map((row) => row.module).sort()).toEqual(['pms', 'spa']);
    expect(split.idle.map((row) => row.module)).toEqual(['mice']);
    expect(split.active).toBe(1);
  });

  it('lists only the missing items, each opening the screen that adds it', () => {
    const onOpen = vi.fn();
    render(<ModuleSetupList modules={modules} onOpen={onOpen} />);
    const spa = screen.getByTestId('setup-module-spa');
    expect(spa).toHaveTextContent('Terapist');
    expect(spa).not.toHaveTextContent('SPA hizmeti');
    fireEvent.click(screen.getAllByRole('button', { name: /Tamamla/ })[1]);
    expect(onOpen).toHaveBeenCalledWith('/spa-wellness');
    expect(screen.getByTestId('module-setup-idle')).toHaveTextContent('(1)');
  });

  it('says so when every enabled module is set up', () => {
    render(<ModuleSetupList modules={{ housekeeping: modules.housekeeping }} onOpen={() => {}} />);
    expect(screen.getByTestId('module-setup-complete')).toHaveTextContent('1 modül kullanımda');
  });

  it('keeps known missing setup visible when a usage check is unavailable', () => {
    const agency = { module: 'agency_extranet', status: 'unknown', setup: [
      { key: 'listing', label: 'Tesis vitrini yayında', ok: true },
      { key: 'contract', label: 'Onaylı acente sözleşmesi', ok: false, path: '/app/incoming-agency-contracts' },
    ], usage: [{ key: 'bookings', label: 'Son 30 günde acente rezervasyonu', ok: null }] };
    const onOpen = vi.fn();
    render(<ModuleSetupList modules={{ agency_extranet: agency }} onOpen={onOpen} />);
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
    expect(screen.getByTestId('setup-module-agency_extranet')).toHaveTextContent('Onaylı acente sözleşmesi');
    expect(screen.queryByText('Tesis vitrini yayında')).not.toBeInTheDocument();
    expect(screen.getByTestId('module-setup-usage-unknown')).toHaveTextContent('Kullanım bilgisi alınamadı');
    fireEvent.click(screen.getByRole('button', { name: /Tamamla/ }));
    expect(onOpen).toHaveBeenCalledWith('/app/incoming-agency-contracts');
  });

  it('does not invent missing configuration or a completion action for an unknown setup check', () => {
    const unknown = { module: 'spa', status: 'unknown', setup: [
      { key: 'services', label: 'SPA hizmeti', ok: null, path: '/spa-wellness' },
    ], usage: [] };
    const split = splitReadiness({ spa: unknown });
    expect(split.incomplete).toEqual([]);
    expect(split.unverified).toEqual([unknown]);
    expect(split.complete).toBe(false);
    render(<ModuleSetupList modules={{ spa: unknown }} onOpen={vi.fn()} />);
    expect(screen.getByText(/SPA hizmeti — henüz doğrulanamadı/)).toBeInTheDocument();
    expect(screen.getByTestId('setup-unverified-spa')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Tamamla/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
  });

  it('shows both missing and unverified checks without duplicating the module', () => {
    render(<ModuleSetupList modules={{ spa: { module: 'spa', status: 'unknown', setup: [
      { key: 'services', label: 'SPA hizmeti', ok: false, path: '/spa-wellness' },
      { key: 'rooms', label: 'SPA odası', ok: null },
    ], usage: [] } }} onOpen={vi.fn()} />);
    expect(screen.getAllByTestId('setup-module-spa')).toHaveLength(1);
    expect(screen.getByRole('button', { name: /Tamamla/ })).toBeInTheDocument();
    expect(screen.getByText(/SPA odası — henüz doğrulanamadı/)).toBeInTheDocument();
  });

  it('allows verified setup to complete when only usage is unavailable', () => {
    const agency = { module: 'agency_extranet', status: 'unknown', setup: [
      { key: 'contract', label: 'Onaylı acente sözleşmesi', ok: true },
    ], usage: [{ key: 'bookings', label: 'Son 30 günde acente rezervasyonu', ok: null }] };
    expect(splitReadiness({ agency_extranet: agency }).complete).toBe(true);
    render(<ModuleSetupList modules={{ agency_extranet: agency }} onOpen={vi.fn()} />);
    expect(screen.getByTestId('module-setup-complete')).toBeInTheDocument();
    expect(screen.getByTestId('module-setup-usage-unknown')).toBeInTheDocument();
    expect(screen.queryByTestId('module-setup-idle')).not.toBeInTheDocument();
  });

  it('does not require setup for a usage-only module or a ready view', () => {
    expect(splitReadiness({
      guests: { module: 'guests', status: 'unknown', setup: [], usage: [{ key: 'guests', ok: null }] },
      dashboard: { module: 'dashboard', status: 'ready', view: true, setup: [], usage: [] },
      hr: modules.hr,
    }).complete).toBe(true);
  });

  it.each(['agency_extranet', 'future_module'])('keeps undefined readiness rules unverified (%s)', (module) => {
    const row = { module, status: 'unknown', setup: [], usage: [] };
    expect(splitReadiness({ [module]: row }).complete).toBe(false);
    render(<ModuleSetupList modules={{ [module]: row }} onOpen={vi.fn()} />);
    expect(screen.getByTestId(`setup-unverified-${module}`)).toBeInTheDocument();
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
  });

  it.each([
    null,
    undefined,
    [],
    { spa: null },
    { spa: { ...modules.spa, setup: null } },
    { spa: { ...modules.spa, usage: [null] } },
    { spa: { ...modules.spa, setup: [{ key: 'bad', ok: 'true' }] } },
    { spa: { ...modules.spa, module: 'hr' } },
  ])('does not interpret an invalid or absent payload as completed: %j', (value) => {
    expect(isReadinessMap(value)).toBe(false);
    expect(splitReadiness(value).complete).toBe(false);
    render(<ModuleSetupList modules={value} onOpen={vi.fn()} />);
    expect(screen.queryByTestId('module-setup-complete')).not.toBeInTheDocument();
    expect(screen.getByText(/Modül bilgileri doğrulanamadı/)).toBeInTheDocument();
  });

  it('accepts a verified empty module map', () => {
    expect(isReadinessMap({})).toBe(true);
    expect(splitReadiness({}).complete).toBe(true);
  });
});
