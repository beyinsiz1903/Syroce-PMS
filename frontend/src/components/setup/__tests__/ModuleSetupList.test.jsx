import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ModuleSetupList, { splitReadiness } from '../ModuleSetupList';

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
});
