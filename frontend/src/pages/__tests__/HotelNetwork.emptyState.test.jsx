import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Empty } from '../HotelNetwork';

vi.mock('@/api/axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

describe('HotelNetwork empty state', () => {
  it('can guide the user to a safe next action instead of ending at an empty message', () => {
    render(<Empty text="Aktif paylaşım yok." actions={<button type="button">Anlaşma oluştur</button>} />);

    expect(screen.getByText('Aktif paylaşım yok.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Anlaşma oluştur' })).toBeInTheDocument();
  });
});
