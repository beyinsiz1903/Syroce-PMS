import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { get, post, put, remove, confirmDialog } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  remove: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('axios', () => ({ default: { get, post, put, delete: remove } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

import SocialMediaRadar from '@/pages/SocialMediaRadar';

const rule = {
  id: 'rule-a',
  name: 'Wi-Fi yanıtı',
  keywords: ['wifi', 'internet'],
  reply: 'Ağ bilgilerimiz şöyledir.',
  active: true,
};

describe('SocialMediaRadar automation rules', () => {
  beforeEach(() => {
    get.mockReset().mockResolvedValue({ data: [rule] });
    post.mockReset();
    put.mockReset();
    remove.mockReset().mockResolvedValue({ data: { deleted: true } });
    confirmDialog.mockReset().mockResolvedValue(true);
  });

  afterEach(() => cleanup());

  it('loads, edits and deletes persisted rules', async () => {
    put.mockResolvedValue({ data: { ...rule, name: 'Yeni Wi-Fi yanıtı' } });
    render(<SocialMediaRadar />);

    fireEvent.click(screen.getByRole('tab', { name: /Otomasyon/ }));
    expect(await screen.findByText('Wi-Fi yanıtı')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/social-media/automation-rules');

    fireEvent.click(screen.getByRole('button', { name: 'Düzenle' }));
    fireEvent.change(screen.getByDisplayValue('Wi-Fi yanıtı'), { target: { value: 'Yeni Wi-Fi yanıtı' } });
    fireEvent.click(screen.getByRole('button', { name: 'Değişiklikleri Kaydet' }));

    await waitFor(() => expect(put).toHaveBeenCalledWith('/social-media/automation-rules/rule-a', {
      name: 'Yeni Wi-Fi yanıtı',
      keywords: ['wifi', 'internet'],
      reply: 'Ağ bilgilerimiz şöyledir.',
      active: true,
    }));
    expect(await screen.findByText('Yeni Wi-Fi yanıtı')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Sil' }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith('/social-media/automation-rules/rule-a'));
    expect(screen.queryByText('Yeni Wi-Fi yanıtı')).not.toBeInTheDocument();
  });
});
