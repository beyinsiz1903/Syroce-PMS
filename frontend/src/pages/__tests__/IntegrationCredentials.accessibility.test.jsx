import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet } = vi.hoisted(() => ({ axiosGet: vi.fn() }));

vi.mock('axios', () => ({ default: { get: axiosGet } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_key, fallback) => fallback || _key }) }));

import IntegrationCredentials from '@/pages/IntegrationCredentials';

describe('IntegrationCredentials accessibility', () => {
  beforeEach(() => {
    axiosGet.mockResolvedValue({
      data: {
        items: [{
          key: 'OPENAI_API_KEY', name: 'OpenAI', category: 'ai', description: 'AI erişim anahtarı', is_set: true, source: 'db',
        }],
      },
    });
  });

  it('makes secret visibility a named keyboard control', async () => {
    render(<IntegrationCredentials />);

    const reveal = await screen.findByRole('button', { name: 'OpenAI anahtarını göster' });
    expect(reveal).toHaveAttribute('title', 'OpenAI anahtarını göster');
    fireEvent.click(reveal);
    expect(screen.getByRole('button', { name: 'OpenAI anahtarını gizle' })).toBeInTheDocument();
  });
});
