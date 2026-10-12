import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';
import { AutomationTab } from '../MessagingDashboard';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key, i18n: { language: 'tr' } }) }));
vi.mock('../../components/ui/select', () => ({
  Select: ({ value, onValueChange, children }) => <select value={value || ''} onChange={(e) => onValueChange(e.target.value)}>{children}</select>,
  SelectTrigger: () => null, SelectValue: () => null,
  SelectContent: ({ children }) => <>{children}</>,
  SelectItem: ({ value, disabled, children }) => <option value={value} disabled={disabled}>{children}</option>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockImplementation(async (url) => ({ data:
    url.endsWith('/automation/rules') ? { rules: [] } :
    url.endsWith('/meta-templates') ? { templates: [{ name: 'welcome', language: 'tr', supported: true, variables_count: 1 }] } :
    url.endsWith('/templates') ? { templates: [] } : {}
  }));
  axios.post.mockResolvedValue({ data: { id: 'rule' } });
});

describe('WhatsApp lifecycle setup', () => {
  it('does not create a rule or send messages on load', async () => {
    render(<AutomationTab />);
    await screen.findByTestId('create-automation-btn');
    expect(axios.post).not.toHaveBeenCalled();
    expect(screen.getByText('Misafirin WhatsApp ileti izni')).toBeInTheDocument();
  });

  it('saves the Meta template language and ordered field mapping', async () => {
    render(<AutomationTab />);
    fireEvent.click(await screen.findByTestId('create-automation-btn'));
    fireEvent.change(screen.getByTestId('automation-name'), { target: { value: 'Giriş mesajı' } });
    const metaSelect = screen.getByRole('option', { name: /welcome · tr/ }).closest('select');
    fireEvent.change(metaSelect, { target: { value: 'meta:welcome:tr' } });
    fireEvent.change(screen.getByRole('option', { name: 'Misafir adı' }).closest('select'), { target: { value: 'misafir_adi' } });
    fireEvent.click(screen.getByTestId('automation-save-btn'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/messaging-center/automation/rules', expect.objectContaining({
      trigger_event: 'checked_in', template_id: 'meta:welcome:tr',
      meta_template: { name: 'welcome', language: 'tr', variables: ['misafir_adi'] },
    })));
    expect(axios.post.mock.calls.every(([url]) => !url.includes('send'))).toBe(true);
  });

  it('shows actionable API validation errors', async () => {
    axios.post.mockRejectedValue({ response: { data: { detail: 'Şablon değişkenleri eksik.' } } });
    render(<AutomationTab />);
    fireEvent.click(await screen.findByTestId('create-automation-btn'));
    fireEvent.change(screen.getByTestId('automation-name'), { target: { value: 'Giriş' } });
    fireEvent.change(screen.getByRole('option', { name: /welcome · tr/ }).closest('select'), { target: { value: 'meta:welcome:tr' } });
    fireEvent.click(screen.getByTestId('automation-save-btn'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Şablon değişkenleri eksik.'));
  });
});
