import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import GlobalSearch from '../GlobalSearch';

const { hasModule, translate } = vi.hoisted(() => ({ hasModule: () => true, translate: (_key, fallback) => fallback }));
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('@/config/navItems', () => ({ NAV_ITEMS: [] }));
vi.mock('@/utils/moduleAccess', () => ({ canAccessPmsTab: () => true, canAccessNavItem: () => true }));
vi.mock('@/context/EntitlementContext', () => ({ useEntitlements: () => ({ hasModule }) }));
const user = { id: 'synthetic-user' };
const delayed = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; };
const type = async query => {
  fireEvent.change(screen.getByPlaceholderText('Misafir, rezervasyon, oda, sayfa ara...'), { target: { value: query } });
  await act(async () => vi.advanceTimersByTimeAsync(301));
};
beforeEach(() => { vi.useFakeTimers(); axios.get.mockReset(); });
afterEach(() => vi.useRealTimers());

describe('global search query isolation', () => {
  it('ignores older in-flight results arriving after the newer query', async () => {
    const slow = delayed();
    axios.get.mockImplementation(url => url.includes('q=Murat') ? slow.promise : Promise.resolve({ data: url.includes('/guests/search') ? [{ id: 'selin', name: 'Selin Demir' }] : [] }));
    render(<GlobalSearch user={user} />);
    await type('Murat');
    await type('Selin');
    expect(screen.getByRole('button', { name: 'Selin Demir' })).toBeInTheDocument();
    await act(async () => slow.resolve({ data: [{ id: 'murat', name: 'Murat Sutay' }] }));
    expect(screen.queryByRole('button', { name: 'Murat Sutay' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Selin Demir' })).toBeInTheDocument();
  });

  it('does not resurrect a cleared query or leak its results into another search', async () => {
    const slow = delayed();
    axios.get.mockImplementation(url => url.includes('q=Murat') ? slow.promise : Promise.resolve({ data: [] }));
    render(<GlobalSearch user={user} />);
    await type('Murat');
    await type('');
    await act(async () => slow.resolve({ data: [{ id: 'murat', name: 'Murat Sutay' }] }));
    await type('Selin');
    expect(screen.queryByText('Murat Sutay')).not.toBeInTheDocument();
    expect(screen.getByText('Sonuç bulunamadı')).toBeInTheDocument();
  });

  it('emits the selected guest identity and clears the completed search', async () => {
    const guest = { id: 'murat', name: 'Murat Sutay' }, onSelectResult = vi.fn();
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('/guests/search') ? [guest] : [] }));
    render(<GlobalSearch user={user} onSelectResult={onSelectResult} />);
    await type('Murat');
    fireEvent.click(screen.getByRole('button', { name: 'Murat Sutay' }));
    expect(onSelectResult).toHaveBeenCalledWith({ type: 'guest', data: guest });
    expect(screen.getByRole('textbox')).toHaveValue('');
  });
});
