import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('axios', () => ({ default: api }));
import DataMigrationPage, { migrationError } from '@/pages/DataMigrationPage';

const dataset = { id: 'd1', entity: 'guests', row_count: 1, mapping: { source_id: 'source_id', name: 'name' }, headers: ['source_id', 'name'], date_format: '%Y-%m-%d', decimal_separator: '.', value_mapping: {}, guest_links: {} };
const draft = { id: 'b1', source: 'Synthetic PMS', namespace: 'legacy-2026', publish_guests: false, revision: 2, datasets: [dataset], state: 'draft', cursor: 0 };
const report = { rows: 1, error_count: 0, errors: [], errors_truncated: false, warnings: [{ message: 'Bağımsız kaynak mutabakatı eksik.' }], all_source_reconciled: false, active_reservations_archive_only: 0, datasets: [{ dataset_id: 'd1', entity: 'guests', rows: 1, create: 1, reuse: 0, totals: {}, unmapped_columns: [] }] };
const reviewed = { ...draft, state: 'reviewed', report, review_token: 'a'.repeat(64) };
let current;

function mount(props = {}, path = '/app/data-migration') {
  return render(<MemoryRouter initialEntries={[path]}><DataMigrationPage {...props} /></MemoryRouter>);
}

async function openBatch() {
  fireEvent.click(await screen.findByRole('button', { name: /Synthetic PMS/ }));
  await screen.findByRole('region', { name: 'Seçili aktarım' });
}

beforeEach(() => {
  vi.clearAllMocks(); current = structuredClone(draft);
  api.get.mockImplementation(async url => {
    if (url.endsWith('/schema')) return { data: { entities: { guests: { fields: ['source_id', 'name'], required: ['source_id', 'name'] } } } };
    if (url.endsWith('/mapping-templates')) return { data: { items: [] } };
    if (url.endsWith('/batches')) return { data: { items: [current], total: 1 } };
    if (url.endsWith('/batches/b1')) return { data: current };
    if (url.endsWith('/archive')) return { data: { total: 0, items: [], offset: 0, limit: 25 } };
    throw new Error(`Unexpected GET ${url}`);
  });
  api.put.mockResolvedValue({ data: draft });
  api.post.mockImplementation(async url => {
    if (url.endsWith('/review')) return { data: reviewed };
    if (url.endsWith('/commit')) return { data: { ...reviewed, state: 'complete', cursor: 1 } };
    if (url.endsWith('/files')) return { data: draft };
    if (url.endsWith('/batches')) return { data: { ...draft, datasets: [] } };
    if (url.endsWith('/rollback')) return { data: { ...reviewed, state: 'rolled_back' } };
    throw new Error(`Unexpected POST ${url}`);
  });
  api.delete.mockResolvedValue({ data: { ...draft, datasets: [] } });
});

describe('Data migration workbench', () => {
  it('states the archive / live cutover boundary and keeps guest publication opt-in', async () => {
    mount();
    expect(await screen.findByText(/ayrı canlı devir adımı ve açılış fişi onayı gerekir/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Misafir profillerini normal/)).not.toBeChecked();
    expect(screen.getByRole('button', { name: /Yeni aktarım oluştur/ })).toBeEnabled();
  });

  it('creates a source-neutral batch without a client-supplied tenant', async () => {
    mount(); await screen.findByRole('button', { name: /Synthetic PMS/ });
    fireEvent.change(screen.getByLabelText('Kaynak PMS / dosya açıklaması'), { target: { value: 'Any PMS' } });
    fireEvent.change(screen.getByLabelText('Kalıcı kaynak anahtarı'), { target: { value: 'old-system' } });
    fireEvent.click(screen.getByRole('button', { name: /Yeni aktarım oluştur/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/data-migration/batches', { source: 'Any PMS', namespace: 'old-system', publish_guests: false, allow_archive_updates: false }));
  });

  it('uploads the file with its declared data type and no fabricated rows', async () => {
    mount(); await openBatch();
    const file = new File(['source_id,name\ng1,Synthetic'], 'source.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('Dosya'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Dosyayı ekle' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/data-migration/batches/b1/files', expect.any(FormData)));
    const form = api.post.mock.calls.find(([url]) => url.endsWith('/files'))[1];
    expect(form.get('file')).toBe(file); expect(form.get('entity')).toBe('guests');
  });

  it('saves explicit field mapping and source count', async () => {
    mount(); await openBatch();
    fireEvent.change(screen.getByLabelText('Kaynak raporundaki kayıt sayısı'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Eşleştirmeyi kaydet' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/data-migration/batches/b1/datasets/d1', expect.objectContaining({ expected_count: 1, mapping: dataset.mapping, guest_links: {} })));
  });

  it('requires the dry run and explicit acknowledgement before committing', async () => {
    mount(); await openBatch();
    expect(screen.queryByRole('button', { name: '4. Onayla ve aktar' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '3. Deneme aktarımı ve mutabakat' }));
    const commit = await screen.findByRole('button', { name: '4. Onayla ve aktar' });
    expect(commit).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Eşleştirmeleri, eksik kaynak/));
    fireEvent.click(commit);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/data-migration/batches/b1/commit', { review_token: 'a'.repeat(64), archive_only_ack: true, warnings_ack: true }, expect.any(Object)));
    expect(await screen.findByText(/Arşiv aktarımı tamamlandı. Oda takvimi/)).toBeInTheDocument();
  });

  it('does not enable commit when the dry run has errors', async () => {
    current = { ...reviewed, report: { ...report, error_count: 1, errors: [{ row: 2, message: 'Kaynak bağlantısı eksik' }] } };
    mount(); await openBatch();
    fireEvent.click(screen.getByLabelText(/Eşleştirmeleri, eksik kaynak/));
    expect(screen.getByRole('button', { name: '4. Onayla ve aktar' })).toBeDisabled();
    expect(screen.getByText('Satır 2: Kaynak bağlantısı eksik')).toBeInTheDocument();
  });

  it('cannot approve a stale preview while edited mapping is unsaved', async () => {
    current = structuredClone(reviewed);
    mount(); await openBatch();
    fireEvent.click(screen.getByLabelText(/Eşleştirmeleri, eksik kaynak/));
    expect(screen.getByRole('button', { name: '4. Onayla ve aktar' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('Kaynak raporundaki kayıt sayısı'), { target: { value: '1' } });
    expect(screen.getByText(/Kaydedilmemiş eşleştirme değişiklikleri/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '4. Onayla ve aktar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '3. Deneme aktarımı ve mutabakat' })).toBeDisabled();
  });

  it('resumes a failed batch using the original approved token', async () => {
    current = { ...reviewed, state: 'failed' };
    mount(); await openBatch();
    fireEvent.click(screen.getByLabelText(/Eşleştirmeleri, eksik kaynak/));
    fireEvent.click(screen.getByRole('button', { name: 'Kaldığı yerden devam et' }));
    expect(await screen.findByText(/Arşiv aktarımı tamamlandı. Oda takvimi/)).toBeInTheDocument();
  });

  it('requires typed rollback confirmation and never offers deletion of published profiles', async () => {
    current = { ...reviewed, state: 'complete', publish_guests: true };
    mount(); await openBatch();
    expect(screen.queryByText('Kontrollü arşiv geri alma')).not.toBeInTheDocument();
  });

  it('filters imported history from a guest card deep link', async () => {
    mount({}, '/app/data-migration?guest_id=guest-1');
    fireEvent.click(await screen.findByRole('button', { name: 'Arşivi getir' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/data-migration/archive', { params: expect.objectContaining({ guest_id: 'guest-1', offset: 0, limit: 25 }) }));
  });

  it('shows API failures without exposing a raw validation object', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Bu alana erişim yok.' } } });
    mount(); expect(await screen.findByRole('alert')).toHaveTextContent('Bu alana erişim yok.');
    expect(migrationError({ response: { data: { detail: [{ input: 'sensitive' }] } } })).not.toContain('sensitive');
  });

  it('resets cached migration and archive state when the selected hotel changes', async () => {
    const view = mount({ user: { tenant_id: 'A' } }); await openBatch();
    current = { ...draft, id: 'hotel-b-batch', source: 'Other hotel', datasets: [] };
    view.rerender(<MemoryRouter><DataMigrationPage user={{ tenant_id: 'B' }} /></MemoryRouter>);
    expect(await screen.findByRole('button', { name: /Other hotel/ })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Seçili aktarım' })).not.toBeInTheDocument();
  });
});
