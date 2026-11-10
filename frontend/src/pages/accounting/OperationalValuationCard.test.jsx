import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import OperationalValuationCard from './OperationalValuationCard';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));

const runs = [
  { id: 'another-run', business_date: '2026-10-31' },
  { id: 'selected-run', business_date: '2026-10-30' },
];
const endpoint = '/gl/integrations/operational/night-audit/selected-run/valuation';
const previewHash = 'a'.repeat(64);
const preview = {
  run_id: 'selected-run', business_date: '2026-10-30', action: 'post', preview_hash: previewHash,
  manifest: { sources: [{ id: 'source-1' }] },
  posting_lines: [{ account_code: '120', debit: 1500.42 }, { account_code: '600', credit: 1500.42 }],
};
const payload = { business_date: '2026-10-30', base_currency: 'TRY', rates_to_try: { USD: '49.7747' }, reference: 'TCMB dated bulletin' };

function fillValuation() {
  fireEvent.change(screen.getByLabelText('USD / TRY'), { target: { value: '49,7747' } });
  fireEvent.change(screen.getByLabelText('Kur kaynağı ve referansı'), { target: { value: 'TCMB dated bulletin' } });
  fireEvent.click(screen.getByRole('button', { name: 'Aktarımı Önizle' }));
}

describe('OperationalValuationCard', () => {
  beforeEach(() => axios.post.mockReset());

  it('posts only the exact reviewed source-day valuation and preserves cents in the preview', async () => {
    axios.post.mockResolvedValueOnce({ data: preview }).mockResolvedValueOnce({ data: { status: 'posted', entry_id: 'journal-1' } });
    const onPosted = vi.fn();
    render(<OperationalValuationCard runs={runs} requestedRunId="selected-run" onPosted={onPosted} />);
    expect(screen.queryByRole('button', { name: 'Önizlemeyi Onayla ve Kaydet' })).not.toBeInTheDocument();
    fillValuation();
    const confirm = await screen.findByRole('button', { name: 'Önizlemeyi Onayla ve Kaydet' });
    expect(axios.post).toHaveBeenNthCalledWith(1, `${endpoint}/preview`, payload);
    expect(screen.getAllByText(/1\.500,42/)).toHaveLength(4);
    fireEvent.click(confirm);
    expect(await screen.findByText(/Fiş kimliği journal-1/)).toBeInTheDocument();
    expect(axios.post).toHaveBeenNthCalledWith(2, `${endpoint}/post`, { ...payload, expected_preview_hash: previewHash });
    expect(onPosted).toHaveBeenCalledTimes(1);
  });

  it('invalidates confirmation when source inputs or the run change, and shows a backend rejection', async () => {
    axios.post.mockResolvedValueOnce({ data: preview }).mockRejectedValueOnce({ response: { data: { detail: 'Kaynak değişti' } } });
    render(<OperationalValuationCard runs={runs} requestedRunId="selected-run" />);
    fillValuation();
    await screen.findByRole('button', { name: 'Önizlemeyi Onayla ve Kaydet' });
    fireEvent.change(screen.getByLabelText('EUR / TRY'), { target: { value: '55,7149' } });
    expect(screen.queryByRole('button', { name: 'Önizlemeyi Onayla ve Kaydet' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Aktarımı Önizle' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Kaynak değişti');
    fireEvent.change(screen.getByLabelText('Kaynak iş günü'), { target: { value: 'another-run' } });
    await waitFor(() => expect(screen.getByLabelText('USD / TRY')).toHaveValue(''));
    expect(axios.post).toHaveBeenCalledTimes(2);
  });

  it('allows an existing journal to be relinked after a partial response', async () => {
    axios.post.mockResolvedValueOnce({ data: { ...preview, action: 'already_posted' } })
      .mockResolvedValueOnce({ data: { status: 'already_posted', entry_id: 'existing-journal' } });
    render(<OperationalValuationCard runs={runs} requestedRunId="selected-run" />);
    fillValuation();
    fireEvent.click(await screen.findByRole('button', { name: 'Fiş Bağlantısını Doğrula' }));
    expect(await screen.findByText(/Fiş kimliği existing-journal/)).toBeInTheDocument();
    expect(axios.post).toHaveBeenNthCalledWith(2, `${endpoint}/post`, { ...payload, expected_preview_hash: previewHash });
  });
});
