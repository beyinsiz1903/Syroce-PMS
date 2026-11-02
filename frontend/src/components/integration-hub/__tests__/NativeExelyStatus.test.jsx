import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import NativeExelyStatus from '../NativeExelyStatus';

it.each([
  { state: 'ready', connected: true, ariEnabled: false, writeAllowed: true },
  { state: 'ready', connected: true, ariEnabled: true, writeAllowed: false, blockReason: 'EXELY_GLOBAL_GATE_CLOSED' },
  { state: 'ready', connected: false, ariEnabled: true, writeAllowed: true },
])('never reports open writes when a required source is disabled: %j', status => {
  render(<MemoryRouter><NativeExelyStatus status={status} /></MemoryRouter>);
  expect(screen.getByTestId('native-exely-ari-state')).toHaveTextContent('kapalı / engelli');
  expect(screen.queryByText('ARI gönderimi açık')).not.toBeInTheDocument();
});

it('fails visibly on read error without retaining a stale active state', () => {
  const retry = vi.fn();
  const { rerender } = render(<MemoryRouter><NativeExelyStatus status={{ state: 'ready', connected: true, ariEnabled: true, writeAllowed: true }} /></MemoryRouter>);
  expect(screen.getByText('ARI gönderimi açık')).toBeInTheDocument();
  rerender(<MemoryRouter><NativeExelyStatus status={{ state: 'error' }} onRetry={retry} /></MemoryRouter>);
  expect(screen.queryByText('ARI gönderimi açık')).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('Durumu tekrar kontrol et'));
  expect(retry).toHaveBeenCalledOnce();
});
