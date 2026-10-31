import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, toast } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() }, toast: vi.fn() }));
vi.mock('@/api/axios', () => ({ default: api }));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
import ProfileUdfPage from '@/pages/ProfileUdfPage';

const definition = { id: 'score-def', key: 'score', label: 'QA score', type: 'number', required: true, active: true, options: [] };
const initial = { guest_name: 'Synthetic QA', definitions: [definition], values: { score: 0, legacy_unselected: 'preserve server source' }, revision: 'a'.repeat(64) };

async function selectGuest() {
  render(<ProfileUdfPage />);
  await screen.findByText('Evet');
  fireEvent.mouseDown(screen.getByTestId('tab-udf-values'), { button: 0, ctrlKey: false });
  fireEvent.change(await screen.findByTestId('input-udf-search'), { target: { value: 'Synthetic QA' } });
  fireEvent.click(screen.getByTestId('button-udf-search'));
  fireEvent.click(await screen.findByRole('button', { name: 'cm.pages_ProfileUdfPage.sec' }));
  await screen.findByTestId('udf-input-score');
}

describe('Profile UDF source-version contract', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
    vi.clearAllMocks();
    api.get.mockImplementation(async path => ({ data: path === '/profile-udf/definitions' ? [definition] : path === '/pms/guests/search' ? [{ id: 'guest', name: 'Synthetic QA' }] : initial }));
    api.put.mockResolvedValue({ data: { values: { score: 12.5, legacy_unselected: 'preserve server source' }, revision: 'b'.repeat(64) } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('shows required flags and saves with the exact loaded source revision', async () => {
    await selectGuest();
    fireEvent.change(screen.getByTestId('udf-input-score'), { target: { value: '12.5' } });
    fireEvent.click(screen.getByTestId('button-udf-save'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/profile-udf/guests/guest', { values: { score: '12.5' }, expected_revision: initial.revision }));
    await waitFor(() => expect(screen.getByTestId('udf-input-score')).toHaveValue(12.5));
    fireEvent.click(screen.getByTestId('button-udf-save'));
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith('/profile-udf/guests/guest', { values: { score: 12.5 }, expected_revision: 'b'.repeat(64) }));
  });

  it('blocks blind retries after conflict until an explicit reload', async () => {
    api.put.mockRejectedValue({ response: { status: 409, data: { detail: 'Kaynak değişti' } } });
    await selectGuest();
    fireEvent.click(screen.getByTestId('button-udf-save'));
    await waitFor(() => expect(screen.getByTestId('button-udf-save')).toBeDisabled());
    expect(screen.getByRole('alert')).toHaveTextContent('yeniden yükleyin');
    fireEvent.click(screen.getByTestId('button-udf-save'));
    expect(api.put).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: 'Misafiri yeniden yükle' }));
    await waitFor(() => expect(screen.getByTestId('button-udf-save')).toBeEnabled());
    expect(api.get).toHaveBeenLastCalledWith('/profile-udf/guests/guest');
  });

  it('fails closed if an older API omits the source revision', async () => {
    api.get.mockImplementation(async path => ({ data: path === '/profile-udf/definitions' ? [definition] : path === '/pms/guests/search' ? [{ id: 'guest' }] : { ...initial, revision: undefined } }));
    await selectGuest();
    expect(screen.getByTestId('button-udf-save')).toBeDisabled();
    expect(api.put).not.toHaveBeenCalled();
  });
});
