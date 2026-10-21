import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useSearchParams } from 'react-router-dom';
import { Archive, ArrowRight, Database, Download, RefreshCw, ShieldCheck, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import DataMigrationCutover from './DataMigrationCutover';

const ROOT = '/data-migration';
const ENTITIES = { guests: 'Misafirler', companies: 'Şirketler', agencies: 'Acenteler', rooms: 'Odalar', reservations: 'Rezervasyon / konaklama geçmişi', folios: 'Folyolar', daily_rates: 'Brüt günlük oda fiyatları', transactions: 'Finans hareketleri', balances: 'Açık bakiyeler' };
const STATES = { draft: 'Hazırlanıyor', reviewed: 'Deneme tamamlandı', importing: 'Aktarım sürüyor', complete: 'Arşiv aktarımı tamamlandı', failed: 'Durduruldu · devam edilebilir', rolling_back: 'Geri alınıyor', rolled_back: 'Geri alındı' };
const FIELDS = { source_id: 'Eski kayıt numarası', name: 'Ad soyad / unvan', email: 'E-posta', phone: 'Telefon', id_number: 'Kimlik / pasaport no', nationality: 'Uyruk', address: 'Adres', birth_date: 'Doğum tarihi', notes: 'Notlar', preferences: 'Tercihler', room_number: 'Oda numarası', room_type: 'Oda tipi', floor: 'Kat', capacity: 'Kapasite', guest_source_id: 'Eski misafir no', company_source_id: 'Eski şirket no', agency_source_id: 'Eski acente no', room_source_id: 'Eski oda no', reservation_source_id: 'Eski rezervasyon no', folio_source_id: 'Eski folyo no', check_in: 'Giriş tarihi', check_out: 'Çıkış tarihi', status: 'Durum', adults: 'Yetişkin', children: 'Çocuk', total_amount: 'Rezervasyon bedeli', currency: 'Para birimi', balance: 'Bakiye', transaction_date: 'Hareket tarihi', balance_date: 'Bakiye tarihi', kind: 'İşlem türü', amount: 'Tutar', description: 'Açıklama', reference: 'Belge referansı', tax_number: 'Vergi numarası', marketing_consent: 'Pazarlama izni', consent_date: 'İzin tarihi', consent_reference: 'İzin kanıtı referansı' };
const selectClass = 'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm';
const textClass = 'min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm font-mono';

export function migrationError(error) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : 'İşlem tamamlanamadı. Durumu yenileyip tekrar deneyin.';
}

async function download(path, filename) {
  const { data } = await axios.get(path, { responseType: 'blob' });
  const url = URL.createObjectURL(data);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ArchiveDetail({ detail, busy, onClose, onOpenRelated, onChildren }) {
  return <section className="space-y-3 rounded-md border bg-muted/30 p-4" aria-label="Arşiv kayıt detayı">
    <div className="flex justify-between gap-2"><h3 className="break-all font-semibold">{ENTITIES[detail.entity]} · {detail.data.source_id}</h3><Button size="sm" variant="outline" onClick={onClose}>Kapat</Button></div>
    <p className="text-xs">Aktarım durumu: {STATES[detail.batch_state] || detail.batch_state || 'Bilinmiyor'}</p>
    <dl className="grid gap-3 sm:grid-cols-2">
      {Object.entries(detail.data).map(([key, value]) => <div key={key} className="min-w-0">
        <dt className="text-xs text-muted-foreground">{key === 'source_fields' ? 'Eski PMS’ye özel ek alanlar' : FIELDS[key] || key}</dt>
        <dd className="whitespace-pre-wrap break-words text-sm">{typeof value === 'boolean' ? (value ? 'Evet' : 'Hayır') : typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : String(value ?? '')}</dd>
      </div>)}
    </dl>
    <div className="flex flex-wrap gap-2">
      {Object.entries(detail.refs || {}).map(([field, key]) => <Button key={field} size="sm" variant="outline" disabled={busy} onClick={() => onOpenRelated(key)}>{FIELDS[field] || field} kaydını aç</Button>)}
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onChildren(detail.id)}>Bağlı alt kayıtları getir</Button>
    </div>
    <p className="break-all text-xs text-muted-foreground">Aktarım: {detail.owner_batch_id}</p>
    <ArchiveDocuments key={detail.id} recordId={detail.id} />
  </section>;
}

function ArchiveDocuments({ recordId }) {
  const [items, setItems] = useState([]);
  const [versions, setVersions] = useState(null);
  const [sourceId, setSourceId] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(fn) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(migrationError(e)); } finally { setBusy(false); } }
  async function refresh() { setItems((await axios.get(`${ROOT}/archive/${recordId}/attachments`)).data.items); }
  return <details className="space-y-3 rounded-md border p-3"><summary className="cursor-pointer text-sm font-medium">Ek belgeler ve önceki arşiv sürümleri</summary>
    <p className="text-xs text-muted-foreground">PDF/görseller şifreli ve indirme amaçlı saklanır; belge başına 5 MB, kayıt başına 20 ek. Kimlik/izin doğrulaması sayılmaz. İndirilen belgeleri güvenli cihazda açın.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={busy} onClick={() => run(refresh)}>Ek belgeleri listele</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => run(async () => setVersions((await axios.get(`${ROOT}/archive/${recordId}/versions`)).data))}>Önceki sürümleri göster</Button></div>
    {items.map(item => <div key={item.id} className="flex flex-wrap items-center gap-2 text-xs"><span>{item.content_type} · {item.size} bayt</span><Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => download(`${ROOT}/attachments/${item.id}/download`, 'kaynak-belge' + ({ 'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/gif': '.gif' }[item.content_type] || '.bin')))}>Belgeyi indir</Button></div>)}
    {versions && <div className="space-y-2 text-xs">{versions.items.length === 0 ? <p>Önceki sürüm yok.</p> : versions.items.map((item, i) => <details key={i}><summary>{String(item.archived_at)} · {item.replaced_by_batch}</summary><pre className="whitespace-pre-wrap break-all">{JSON.stringify(item.data, null, 2)}</pre></details>)}{versions.truncated && <p>İlk 100 sürüm gösteriliyor.</p>}</div>}
    <form className="space-y-2" onSubmit={e => { e.preventDefault(); run(async () => { const body = new FormData(); body.append('source_id', sourceId); body.append('file', file); await axios.post(`${ROOT}/archive/${recordId}/attachments`, body); setSourceId(''); await refresh(); }); }}>
      <Label htmlFor="archive-document-id">Kaynak ek belge kimliği</Label><Input id="archive-document-id" value={sourceId} maxLength={160} required disabled={busy} onChange={e => setSourceId(e.target.value)} />
      <Label htmlFor="archive-document-file">Kaynak ek belge</Label><Input id="archive-document-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.gif" required disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)} />
      <Button size="sm" type="submit" disabled={busy || !file || !sourceId}>Belgeyi şifreli arşive ekle</Button>
    </form>
  </details>;
}

function DatasetEditor({ dataset, schema, busy, onSave, onRemove, templates, onTemplate, onDirty }) {
  const [mapping, setMapping] = useState(dataset.mapping);
  const [dateFormat, setDateFormat] = useState(dataset.date_format);
  const [decimal, setDecimal] = useState(dataset.decimal_separator);
  const [count, setCount] = useState(dataset.expected_count ?? '');
  const [totals, setTotals] = useState(dataset.expected_totals ? JSON.stringify(dataset.expected_totals, null, 2) : '');
  const [codes, setCodes] = useState(JSON.stringify(dataset.value_mapping || {}, null, 2));
  const [links, setLinks] = useState(JSON.stringify(dataset.guest_links || {}, null, 2));
  const [templateName, setTemplateName] = useState('');
  const [error, setError] = useState('');
  const [completeFolios, setCompleteFolios] = useState(dataset.folio_transactions_complete || false);
  const [preserveExtras, setPreserveExtras] = useState(dataset.preserve_extra_fields || false);
  const prefix = dataset.id;
  function body() {
    return { mapping, date_format: dateFormat, decimal_separator: decimal, expected_count: count === '' ? null : Number(count), expected_totals: totals.trim() ? JSON.parse(totals) : null, value_mapping: JSON.parse(codes), guest_links: JSON.parse(links), folio_transactions_complete: completeFolios, preserve_extra_fields: preserveExtras };
  }
  async function save(event) {
    event.preventDefault(); setError('');
    try { await onSave(body()); } catch (e) { setError(e instanceof SyntaxError ? 'JSON alanlarından biri geçersiz.' : migrationError(e)); }
  }
  function applyTemplate(id) {
    const item = templates.find(t => t.id === id);
    if (!item) return;
    setMapping(Object.fromEntries(Object.entries(item.mapping).filter(([, column]) => dataset.headers.includes(column))));
    setDateFormat(item.date_format); setDecimal(item.decimal_separator); setCodes(JSON.stringify(item.value_mapping, null, 2)); setPreserveExtras(item.preserve_extra_fields || false);
  }
  return <Card>
    <CardHeader><CardTitle className="text-base">{ENTITIES[dataset.entity]} · {dataset.row_count} satır</CardTitle></CardHeader>
    <CardContent><form onSubmit={save} onChange={onDirty} className="space-y-4">
      <p className="text-sm text-muted-foreground">* zorunlu alan. Eşleştirilmemiş sütunlar, ek alanları koruma seçilmediyse nihai arşive taşınmaz. Kayıt numarası yerine ad soyad kullanmayın.</p>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={preserveExtras} disabled={busy} onChange={e => setPreserveExtras(e.target.checked)} /><span>Eşleştirilmeyen eski PMS sütunlarını da ek kaynak alanları olarak şifreli arşivde koru. Bu alanlar canlı profil/finans alanlarına uygulanmaz.</span></label>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {schema.fields.map(field => <div key={field} className="space-y-1">
          <Label htmlFor={`${prefix}-${field}`}>{FIELDS[field] || field}{schema.required.includes(field) ? ' *' : ''}</Label>
          <select id={`${prefix}-${field}`} className={selectClass} value={mapping[field] || ''} disabled={busy} onChange={e => setMapping(old => { const next = { ...old }; if (e.target.value) next[field] = e.target.value; else delete next[field]; return next; })}>
            <option value="">Aktarılmayacak</option>{dataset.headers.map(h => <option key={h} value={h}>{h}</option>)}
          </select>
        </div>)}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><Label htmlFor={`${prefix}-dates`}>Metin tarih biçimi</Label><select id={`${prefix}-dates`} className={selectClass} value={dateFormat} disabled={busy} onChange={e => setDateFormat(e.target.value)}><option value="%Y-%m-%d">2026-10-21</option><option value="%d.%m.%Y">21.10.2026</option><option value="%d/%m/%Y">21/10/2026</option><option value="%m/%d/%Y">10/21/2026 (ABD)</option></select></div>
        <div><Label htmlFor={`${prefix}-decimal`}>Ondalık ayırıcı</Label><select id={`${prefix}-decimal`} className={selectClass} value={decimal} disabled={busy} onChange={e => setDecimal(e.target.value)}><option value=".">Nokta · 1234.56</option><option value=",">Virgül · 1234,56</option></select></div>
        <div><Label htmlFor={`${prefix}-count`}>Kaynak raporundaki kayıt sayısı</Label><Input id={`${prefix}-count`} type="number" min="0" max="50000" value={count} disabled={busy} onChange={e => setCount(e.target.value)} placeholder="Bağımsız kontrol sayısı" /></div>
      </div>
      <details className="rounded-md border p-3"><summary className="cursor-pointer text-sm font-medium">Kod eşleştirme, kontrol toplamları ve mevcut misafir bağlantıları</summary>
        {dataset.entity === 'folios' && <label className="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" checked={completeFolios} disabled={busy} onChange={e => setCompleteFolios(e.target.checked)} />Bu folyoların tüm hareketleri dosyalarda / önceki arşivde mevcut; hareket toplamı ile bakiyeyi doğrula.</label>}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div><Label htmlFor={`${prefix}-codes`}>Durum / tür / döviz kodları (JSON)</Label><textarea id={`${prefix}-codes`} className={textClass} value={codes} disabled={busy} onChange={e => setCodes(e.target.value)} /><p className="text-xs text-muted-foreground">Örnek: {'{"status":{"OUT":"checked_out"}}'}. Durumlar: checked_out, cancelled, no_show, confirmed, checked_in, pending.</p></div>
          <div><Label htmlFor={`${prefix}-totals`}>Kaynak kontrol toplamları (JSON)</Label><textarea id={`${prefix}-totals`} className={textClass} value={totals} disabled={busy} onChange={e => setTotals(e.target.value)} placeholder={'{"total:TRY":"1200.00"}'} /><p className="text-xs text-muted-foreground">Hareketler: charge/payment/refund/adjustment. Bakiyeler: receivable/payable/deposit. Örnek: {'{"payment:EUR":"100.00"}'}. Farklı dövizler toplanmaz.</p></div>
          {dataset.entity === 'guests' && <div><Label htmlFor={`${prefix}-links`}>Eski misafir no → mevcut Syroce misafir ID (JSON)</Label><textarea id={`${prefix}-links`} className={textClass} value={links} disabled={busy} onChange={e => setLinks(e.target.value)} /><p className="text-xs text-muted-foreground">Yalnız kontrol ettiğiniz eşleşmeleri bağlayın. Mevcut profil bilgileri değiştirilmez.</p></div>}
          <div className="space-y-2"><Label htmlFor={`${prefix}-template`}>Kayıtlı eşleştirmeyi uygula</Label><select id={`${prefix}-template`} className={selectClass} disabled={busy} defaultValue="" onChange={e => applyTemplate(e.target.value)}><option value="">Şablon seçin</option>{templates.filter(t => t.entity === dataset.entity).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select><Input aria-label="Eşleştirme şablonu adı" value={templateName} maxLength={80} disabled={busy} onChange={e => setTemplateName(e.target.value)} placeholder="Şablon adı" /><Button type="button" variant="outline" disabled={busy || templateName.trim().length < 2} onClick={async () => { try { setError(''); await onTemplate(templateName.trim(), body()); } catch (e) { setError(e instanceof SyntaxError ? 'JSON alanlarından biri geçersiz.' : migrationError(e)); } }}>Eşleştirmeyi şablon olarak kaydet</Button></div>
        </div>
      </details>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-2"><Button type="submit" disabled={busy}>Eşleştirmeyi kaydet</Button><Button type="button" variant="outline" disabled={busy} onClick={onRemove}>Dosyayı hazırlıktan çıkar</Button></div>
    </form></CardContent>
  </Card>;
}

export default function DataMigrationPage({ user, tenant } = {}) {
  return <DataMigrationWorkspace key={tenant?.id || user?.tenant_id || 'unscoped'} />;
}

function DataMigrationWorkspace() {
  const [params] = useSearchParams();
  const [schema, setSchema] = useState(null);
  const [batches, setBatches] = useState([]);
  const [batchPage, setBatchPage] = useState({ offset: 0, total: 0 });
  const [templates, setTemplates] = useState([]);
  const [batch, setBatch] = useState(null);
  const [tab, setTab] = useState(params.get('guest_id') ? 'archive' : 'migration');
  const [source, setSource] = useState('');
  const [namespace, setNamespace] = useState('');
  const [publish, setPublish] = useState(false);
  const [allowUpdates, setAllowUpdates] = useState(false);
  const [apiSources, setApiSources] = useState([]);
  const [apiSource, setApiSource] = useState('');
  const [entity, setEntity] = useState('guests');
  const [encoding, setEncoding] = useState('utf-8-sig');
  const [sheet, setSheet] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ack, setAck] = useState(false);
  const [rollbackText, setRollbackText] = useState('');
  const [archive, setArchive] = useState(null);
  const [archiveNamespace, setArchiveNamespace] = useState('');
  const [archiveEntity, setArchiveEntity] = useState('');
  const [guestId, setGuestId] = useState(params.get('guest_id') || '');
  const [detail, setDetail] = useState(null);
  const [parentId, setParentId] = useState('');
  const [dirtyDatasetId, setDirtyDatasetId] = useState(null);
  const fileInput = useRef(null);
  const stop = useRef(false);
  useEffect(() => () => { stop.current = true; }, []);
  const reload = useCallback(async () => {
    const [s, list, saved] = await Promise.all([axios.get(`${ROOT}/schema`), axios.get(`${ROOT}/batches`), axios.get(`${ROOT}/mapping-templates`)]);
    setSchema(s.data); setBatches(list.data.items); setBatchPage({ offset: list.data.offset || 0, total: list.data.total || 0 }); setTemplates(saved.data.items);
  }, []);
  useEffect(() => { reload().catch(e => setError(migrationError(e))); }, [reload]);
  useEffect(() => { axios.get(`${ROOT}/api-sources`).then(({ data }) => setApiSources(data.items || [])).catch(() => setApiSources([])); }, []);
  useEffect(() => { setAck(false); setRollbackText(''); setDirtyDatasetId(null); }, [batch?.id, batch?.revision]);
  useEffect(() => { setFile(null); if (fileInput.current) fileInput.current.value = ''; }, [batch?.id]);
  useEffect(() => { setArchive(null); setDetail(null); setParentId(''); }, [archiveNamespace, archiveEntity, guestId]);
  async function action(fn) {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(migrationError(e)); } finally { setBusy(false); }
  }
  async function create(event) {
    event.preventDefault();
    await action(async () => { const { data } = await axios.post(`${ROOT}/batches`, { source, namespace, publish_guests: publish, allow_archive_updates: allowUpdates }); setBatch(data); await reload(); });
  }
  async function saveDataset(dataset, body) {
    const { data } = await axios.put(`${ROOT}/batches/${batch.id}/datasets/${dataset.id}`, body);
    setBatch(data); setAck(false); return data;
  }
  async function loadBatchPage(offset) {
    await action(async () => { const { data } = await axios.get(`${ROOT}/batches`, { params: { offset, limit: 25 } }); setBatches(data.items); setBatchPage({ offset, total: data.total }); });
  }
  async function importRows() {
    stop.current = false;
    await action(async () => {
      let current = batch;
      do {
        const { data } = await axios.post(`${ROOT}/batches/${current.id}/commit`, { review_token: current.review_token, archive_only_ack: true, warnings_ack: true }, { timeout: 110000 });
        current = data; setBatch(data);
      } while (current.state === 'importing' && !stop.current);
      await reload();
    });
  }
  async function loadArchive(offset = 0, parent = parentId) {
    await action(async () => { const { data } = await axios.get(`${ROOT}/archive`, { params: { namespace: archiveNamespace || undefined, entity: parent ? undefined : archiveEntity || undefined, guest_id: parent ? undefined : guestId || undefined, parent_id: parent || undefined, offset, limit: 25 } }); setArchive(data); setDetail(null); setParentId(parent); });
  }
  async function openRelated(key) {
    await action(async () => { const { data } = await axios.get(`${ROOT}/archive`, { params: { record_id: key, limit: 1 } }); if (!data.items.length) throw new Error('missing'); setDetail(data.items[0]); });
  }
  const editable = batch && ['draft', 'reviewed'].includes(batch.state);
  const resumable = batch && ['importing', 'failed'].includes(batch.state);
  const report = batch?.report;
  return <main className="mx-auto max-w-7xl space-y-5 p-4 md:p-6" data-testid="data-migration-page">
    <PageHeader icon={Database} title="Otel Veri Taşıma Merkezi" subtitle="Kullandığınız PMS'den bağımsız: dosyaları eşleştirin, doğrulayın ve kontrollü aktarın." actions={<Button variant="outline" disabled={busy || !!dirtyDatasetId} onClick={() => action(async () => { await reload(); if (batch) setBatch((await axios.get(`${ROOT}/batches/${batch.id}`)).data); })}><RefreshCw className="mr-2 h-4 w-4" />Yenile</Button>} />
    <div className="rounded-lg border bg-muted/40 p-4 text-sm" role="note"><ShieldCheck className="mr-2 inline h-5 w-5" /><strong>Geçmiş veriler canlı işlemlerden ayrıdır.</strong> Arşiv adımı oda takvimini veya muhasebeyi değiştirmez; ayrı canlı devir adımı ve açılış fişi onayı gerekir. KBS, geçmiş tahsilat, fatura ve mesajlar tekrar gönderilmez. Dosyalar veya sunucuda yetkilendirilmiş JSON API kaynakları kullanılabilir; sağlayıcıya özel API uyarlaması ayrıca doğrulanmalıdır.</div>
    <div className="flex gap-2"><Button variant={tab === 'migration' ? 'default' : 'outline'} onClick={() => setTab('migration')}>Aktarım hazırlığı</Button><Button variant={tab === 'archive' ? 'default' : 'outline'} disabled={!!dirtyDatasetId} onClick={() => setTab('archive')}><Archive className="mr-2 h-4 w-4" />Geçmiş veri arşivi</Button></div>
    {dirtyDatasetId && <p role="status" className="rounded-md border p-3 text-sm">Kaydedilmemiş eşleştirme değişiklikleri var. Diğer dosyaya veya aktarım onayına geçmeden bu dosyayı kaydedin.</p>}
    {error && <div role="alert" className="rounded-md border border-destructive p-3 text-sm text-destructive">{error}</div>}
    {!schema && !error && <p role="status">Veri sözlüğü yükleniyor…</p>}
    {tab === 'migration' && schema && <>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <Card><CardHeader><CardTitle className="text-base">1. Kaynağı tanımlayın</CardTitle></CardHeader><CardContent><form className="space-y-3" onSubmit={create}>
          <div><Label htmlFor="migration-source">Kaynak PMS / dosya açıklaması</Label><Input id="migration-source" value={source} minLength={2} maxLength={80} required onChange={e => setSource(e.target.value)} placeholder="Örn. eski otel yönetim sistemi" /></div>
          <div><Label htmlFor="migration-namespace">Kalıcı kaynak anahtarı</Label><Input id="migration-namespace" value={namespace} minLength={3} maxLength={80} pattern="[a-z0-9][a-z0-9_-]+" required onChange={e => setNamespace(e.target.value)} placeholder="eski-pms-2026" /><p className="mt-1 text-xs text-muted-foreground">Aynı kaynağın tekrar dosyalarında aynı anahtarı kullanın. Bu anahtar kayıtların çoğalmasını önler.</p></div>
          <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} /><span>Misafir profillerini normal misafir listesine de yayınla. Mevcut profiller değişmez. Yayınlanmış profiller otomatik silinmez.</span></label>
          <Button type="submit" disabled={busy || !!dirtyDatasetId}>Yeni aktarım oluştur<ArrowRight className="ml-2 h-4 w-4" /></Button>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={allowUpdates} onChange={e => setAllowUpdates(e.target.checked)} /><span>Son fark aktarımı: değişen arşiv kayıtlarını önceki şifreli sürümleri koruyarak güncelle. Canlıya devredilmiş kaynakta engellenir; mevcut misafir profilleri değiştirilmez.</span></label>
        </form></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-base">Son aktarımlar</CardTitle></CardHeader><CardContent className="space-y-2">
          {!batches.length && <p className="text-sm text-muted-foreground">Henüz aktarım yok. Önce anonim veya yapay bir örnek dosyayla deneyin.</p>}
          {batches.map(item => <button key={item.id} className={`flex w-full flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-left text-sm ${batch?.id === item.id ? 'bg-muted' : 'bg-background'}`} disabled={busy || !!dirtyDatasetId} onClick={() => action(async () => setBatch((await axios.get(`${ROOT}/batches/${item.id}`)).data))}><span className="break-all">{item.source}<span className="block text-xs text-muted-foreground">{item.namespace}</span></span><span>{STATES[item.state] || item.state}</span></button>)}
          {batchPage.total > 25 && <div className="flex gap-2"><Button size="sm" variant="outline" disabled={busy || batchPage.offset === 0} onClick={() => loadBatchPage(Math.max(0, batchPage.offset - 25))}>Önceki aktarımlar</Button><Button size="sm" variant="outline" disabled={busy || batchPage.offset + 25 >= batchPage.total} onClick={() => loadBatchPage(batchPage.offset + 25)}>Sonraki aktarımlar</Button></div>}
        </CardContent></Card>
      </div>
      {batch && <section className="space-y-4" aria-label="Seçili aktarım">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3"><div><h2 className="font-semibold">{batch.source} · {STATES[batch.state]}</h2><p className="text-xs text-muted-foreground break-all">{batch.namespace} · {batch.publish_guests ? 'Arşiv + misafir yayınlama' : 'Yalnız arşiv'} · Revizyon {batch.revision}</p></div><span className="text-sm">İşlenen: {batch.cursor || 0} / {report?.rows || 0}</span></div>
        {editable && <Card><CardHeader><CardTitle className="text-base">2. Dosyaları ekleyin</CardTitle></CardHeader><CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">Dosya başına tek veri türü, en fazla 5 MB / 10.000 satır. Aktarım başına 20 dosya / 50.000 satır. Şifre ve kart verilerini kaldırın. Excel formüllerini değerlere çevirin.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div><Label htmlFor="migration-entity">Veri türü</Label><select id="migration-entity" className={selectClass} value={entity} disabled={busy} onChange={e => setEntity(e.target.value)}>{Object.entries(ENTITIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
            <div><Label htmlFor="migration-encoding">Metin kodlaması</Label><select id="migration-encoding" className={selectClass} value={encoding} disabled={busy} onChange={e => setEncoding(e.target.value)}><option value="utf-8-sig">UTF-8</option><option value="cp1254">Windows Türkçe</option></select></div>
            <div><Label htmlFor="migration-sheet">Excel sayfa adı (çok sayfalıysa)</Label><Input id="migration-sheet" value={sheet} disabled={busy} onChange={e => setSheet(e.target.value)} /></div>
            <div><Label htmlFor="migration-file">Dosya</Label><Input ref={fileInput} id="migration-file" type="file" accept=".csv,.tsv,.xlsx,.json,.xml" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)} /></div>
          </div>
          <div className="flex flex-wrap gap-2">
            {apiSources.length > 0 && <><select aria-label="Yetkili kaynak API" className={selectClass} value={apiSource} disabled={busy} onChange={e => setApiSource(e.target.value)}><option value="">Sunucuda tanımlı API kaynağı</option>{apiSources.map(s => <option key={s.id} value={s.id}>{s.label} · {ENTITIES[s.entity]}</option>)}</select><Button variant="outline" disabled={busy || !!dirtyDatasetId || !apiSource} onClick={() => action(async () => setBatch((await axios.post(`${ROOT}/batches/${batch.id}/api-import`, { source_id: apiSource }, { timeout: 110000 })).data))}>API anlık görüntüsünü oku</Button></>}
            <Button disabled={busy || !!dirtyDatasetId || !file} onClick={() => action(async () => {
              const form = new FormData(); form.append('entity', entity); form.append('encoding', encoding);
              if (sheet) form.append('sheet', sheet); form.append('file', file);
              setBatch((await axios.post(`${ROOT}/batches/${batch.id}/files`, form)).data);
              setFile(null); if (fileInput.current) fileInput.current.value = '';
            })}><Upload className="mr-2 h-4 w-4" />Dosyayı ekle</Button>
            <Button variant="outline" disabled={busy} onClick={() => action(() => download(`${ROOT}/templates/${entity}.csv`, `${entity}-template.csv`))}><Download className="mr-2 h-4 w-4" />Boş CSV şablonu</Button>
          </div>
        </CardContent></Card>}
        {editable && batch.datasets.map(dataset => <DatasetEditor key={`${dataset.id}:${batch.revision}`} dataset={dataset} schema={schema.entities[dataset.entity]} templates={templates} busy={busy || (!!dirtyDatasetId && dirtyDatasetId !== dataset.id)} onDirty={() => setDirtyDatasetId(dataset.id)} onSave={body => action(() => saveDataset(dataset, body))} onRemove={() => action(async () => setBatch((await axios.delete(`${ROOT}/batches/${batch.id}/datasets/${dataset.id}`)).data))} onTemplate={(name, body) => action(async () => { await saveDataset(dataset, body); await axios.post(`${ROOT}/mapping-templates`, { name, batch_id: batch.id, dataset_id: dataset.id }); await reload(); })} />)}
        {editable && <Button disabled={busy || !!dirtyDatasetId || !batch.datasets.length} onClick={() => action(async () => { setAck(false); setBatch((await axios.post(`${ROOT}/batches/${batch.id}/review`, {}, { timeout: 110000 })).data); })}>3. Deneme aktarımı ve mutabakat</Button>}
        {report && <Card><CardHeader><CardTitle className="text-base">Doğrulama sonucu</CardTitle></CardHeader><CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[['Okunabilen kayıt', report.rows], ['Hata', report.error_count], ['Kaynak mutabakatı', report.all_source_reconciled ? 'Tamam' : 'Eksik'], ['Canlıya açılmayan rezervasyon', report.active_reservations_archive_only]].map(([label, value]) => <div key={label} className="rounded-md border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="text-xl font-semibold">{value}</p></div>)}</div>
          {report.datasets.map(d => <div key={d.dataset_id} className="rounded-md border p-3 text-sm"><strong>{ENTITIES[d.entity]}</strong> · {d.rows} satır · {d.create} yeni · {d.reuse} aynı kayıt<p className="text-muted-foreground">{Object.entries(d.totals).map(([key, value]) => `${key}: ${value}`).join(' · ') || 'Parasal toplam yok'}</p>{d.unmapped_columns.length > 0 && <p className="break-words text-muted-foreground">{d.unmapped_preserved ? 'Arşivde korunacak ek sütunlar' : 'Taşınmayacak sütunlar'}: {d.unmapped_columns.join(', ')}</p>}</div>)}
          {report.warnings.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm">{report.warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul>}
          {report.errors.length > 0 && <div className="space-y-2"><ul className="max-h-60 space-y-1 overflow-auto text-sm text-destructive">{report.errors.map((e, i) => <li key={i}>Satır {e.row}: {e.message}</li>)}</ul>{report.errors_truncated && <p className="text-sm">İlk 200 hata gösteriliyor; düzeltip yeniden doğrulayın.</p>}<Button variant="outline" disabled={busy} onClick={() => action(() => download(`${ROOT}/batches/${batch.id}/errors.csv`, 'migration-errors.csv'))}>Hata raporunu indir</Button></div>}
          {(batch.state === 'reviewed' || resumable) && <><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} disabled={busy} /><span>Eşleştirmeleri, eksik kaynak mutabakatını ve taşınmayacak sütunları inceledim. Rezervasyon ve bakiyelerin yalnız arşive taşınacağını; ayrıca canlıya geçiş işlemi gerektiğini onaylıyorum.</span></label><div className="flex gap-2"><Button disabled={busy || !!dirtyDatasetId || !ack || report.error_count > 0} onClick={importRows}>{resumable ? 'Kaldığı yerden devam et' : '4. Onayla ve aktar'}</Button>{busy && <Button variant="outline" onClick={() => { stop.current = true; }}>Bu parçadan sonra duraklat</Button>}</div></>}
          {batch.state === 'complete' && <p role="status" className="text-sm font-medium">Arşiv aktarımı tamamlandı. Oda takvimi ve muhasebe bakiyeleri değiştirilmedi. Geçmiş veri arşivinden kontrol edebilirsiniz.</p>}
          {['complete', 'failed', 'rolling_back'].includes(batch.state) && !batch.publish_guests && <details className="rounded-md border p-3"><summary className="cursor-pointer text-sm">Kontrollü arşiv geri alma</summary><p className="my-2 text-sm text-muted-foreground">Yalnız bu aktarımın oluşturduğu arşiv kayıtlarını kaldırır. Bağımlı aktarım varsa işlem engellenir. Kaynak dosyalar korunur.</p><Label htmlFor="migration-rollback">ARSIVI GERI AL yazın</Label><Input id="migration-rollback" value={rollbackText} onChange={e => setRollbackText(e.target.value)} /><Button className="mt-2" variant="destructive" disabled={busy || rollbackText !== 'ARSIVI GERI AL'} onClick={() => action(async () => { setBatch((await axios.post(`${ROOT}/batches/${batch.id}/rollback`, { confirmation: rollbackText })).data); await reload(); })}>Bu arşiv aktarımını geri al</Button></details>}
        </CardContent></Card>}
        {batch.state === 'complete' && <DataMigrationCutover key={batch.id} batchId={batch.id} />}
      </section>}
    </>}
    {tab === 'archive' && <Card><CardHeader><CardTitle className="text-base">Eski sistemden taşınan kayıtlar</CardTitle></CardHeader><CardContent className="space-y-4">
      <p className="text-sm text-muted-foreground">Arşiv salt okunurdur. Finans geçmişi güncel tahsilat veya rapor geliri değildir. Misafir filtresi profili ve doğrudan bağlı rezervasyon/bakiyeleri getirir.</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Input aria-label="Arşiv kaynak anahtarı" value={archiveNamespace} onChange={e => setArchiveNamespace(e.target.value)} placeholder="Kaynak anahtarı (isteğe bağlı)" /><select aria-label="Arşiv veri türü" className={selectClass} value={archiveEntity} onChange={e => setArchiveEntity(e.target.value)}><option value="">Tüm veri türleri</option>{Object.entries(ENTITIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><Input aria-label="Syroce misafir ID" value={guestId} onChange={e => setGuestId(e.target.value)} placeholder="Syroce misafir ID (isteğe bağlı)" /><Button disabled={busy} onClick={() => loadArchive(0, '')}>Arşivi getir</Button></div>
      {parentId && <p className="break-all text-xs text-muted-foreground">Bağlantılı alt kayıtlar gösteriliyor. Genel filtreye dönmek için Arşivi getir'e basın.</p>}
      {archive && <><p className="text-sm">{archive.total} kayıt · Sayfa {Math.floor(archive.offset / 25) + 1}</p><div className="space-y-2">{archive.items.map(row => <div key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm"><div><strong>{ENTITIES[row.entity]}</strong><p className="break-all text-muted-foreground">{row.namespace} · {row.data.name || row.data.room_number || row.data.source_id}</p></div><Button variant="outline" size="sm" onClick={() => setDetail(row)}>Kaydı incele</Button></div>)}</div><div className="flex gap-2"><Button variant="outline" disabled={busy || archive.offset === 0} onClick={() => loadArchive(Math.max(0, archive.offset - 25))}>Önceki</Button><Button variant="outline" disabled={busy || archive.offset + 25 >= archive.total} onClick={() => loadArchive(archive.offset + 25)}>Sonraki</Button></div></>}
      {detail && <ArchiveDetail detail={detail} busy={busy} onClose={() => setDetail(null)} onOpenRelated={openRelated} onChildren={key => loadArchive(0, key)} />}
    </CardContent></Card>}
  </main>;
}
