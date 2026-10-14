import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowRightLeft, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const currentTenantId = () => {
  try { return JSON.parse(localStorage.getItem('user') || '{}').tenant_id || ''; } catch { return ''; }
};

// Super admin tool: move the active hotel's hotel-bound portal agencies onto
// the marketplace. A dry run is required before the real migration.
export default function LegacyAgencyMigrationDialog({ marketplaceAgencies = [], onDone }) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState(null);
  const [targets, setTargets] = useState({});
  const [selected, setSelected] = useState({});
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const tenantId = currentTenantId();

  const start = async () => {
    setOpen(true); setPreview(null); setPlan(null);
    try {
      const { data } = await axios.get('/marketplace/v1/admin/legacy-migration/preview', { params: { tenant_id: tenantId } });
      setPreview(data);
      setTargets(Object.fromEntries(data.agencies.map(row => [row.legacy_agency.id, row.suggested_target?.id || ''])));
      setSelected(Object.fromEntries(data.agencies.map(row => [row.legacy_agency.id, true])));
    } catch (err) { toast.error(err.response?.data?.detail || 'Taşıma önizlemesi alınamadı.'); setOpen(false); }
  };
  const items = () => (preview?.agencies || [])
    .filter(row => selected[row.legacy_agency.id])
    .map(row => ({ legacy_agency_id: row.legacy_agency.id, marketplace_agency_id: targets[row.legacy_agency.id] || null }));
  const run = async dryRun => {
    if (!items().length) return toast.error('En az bir acente seçin.');
    setBusy(true);
    try {
      const { data } = await axios.post('/marketplace/v1/admin/legacy-migration/execute', { tenant_id: tenantId, items: items(), dry_run: dryRun });
      if (dryRun) { setPlan(data.results); return; }
      const failed = data.results.filter(result => result.error);
      toast[failed.length ? 'error' : 'success'](failed.length ? `${failed.length} acente taşınamadı.` : 'Acenteler marketplace\'e taşındı.');
      setPlan(data.results);
      onDone?.();
    } catch (err) { toast.error(err.response?.data?.detail || 'Taşıma çalıştırılamadı.'); }
    finally { setBusy(false); }
  };

  return (
    <>
      <Button variant="outline" size="sm" onClick={start} disabled={!tenantId} data-testid="legacy-migration-open">
        <ArrowRightLeft className="mr-1.5 h-4 w-4" />Eski portal acentelerini taşı
      </Button>
      <Dialog open={open} onOpenChange={value => !busy && setOpen(value)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Otele bağlı acenteleri marketplace'e taşı</DialogTitle>
            <p className="text-sm text-muted-foreground">Seçili otelin eski portal acenteleri; sözleşme, kullanıcı ve gelecek rezervasyonlarıyla marketplace'e taşınır. Önce önizlemeyi çalıştırın.</p>
          </DialogHeader>
          {!preview ? <div className="py-8 text-center"><Loader2 className="mx-auto animate-spin" /></div> : (
            <div className="max-h-[55vh] space-y-3 overflow-y-auto">
              {preview.notes.map(note => <p key={note} className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">{note}</p>)}
              {preview.agencies.length === 0 && <p className="text-sm text-muted-foreground">Bu otelde taşınacak aktif eski portal acentesi yok.</p>}
              {preview.agencies.map(row => (
                <div key={row.legacy_agency.id} className="rounded-lg border p-3 text-sm">
                  <label className="flex items-center gap-2 font-medium">
                    <input type="checkbox" checked={Boolean(selected[row.legacy_agency.id])} onChange={e => { setPlan(null); setSelected(s => ({ ...s, [row.legacy_agency.id]: e.target.checked })); }} />
                    {row.legacy_agency.name}
                  </label>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {row.contract ? `${row.contract.contract_type} sözleşme · ${row.contract.start_date} – ${row.contract.end_date}` : 'Sözleşme yok'} · {row.user_count} kullanıcı · {row.future_bookings} gelecek rezervasyon
                  </div>
                  <select className="mt-2 h-9 w-full rounded-md border px-2 text-sm" value={targets[row.legacy_agency.id] || ''} onChange={e => { setPlan(null); setTargets(t => ({ ...t, [row.legacy_agency.id]: e.target.value })); }}>
                    <option value="">Yeni marketplace acentesi oluştur</option>
                    {marketplaceAgencies.map(agency => <option key={agency.id} value={agency.id}>Mevcut: {agency.name}</option>)}
                  </select>
                  {row.warnings.map(warning => <p key={warning} className="mt-1 text-xs text-amber-700">{warning}</p>)}
                </div>
              ))}
              {plan && (
                <div className="rounded-lg border bg-slate-50 p-3 text-xs" data-testid="legacy-migration-plan">
                  {plan.map(result => (
                    <div key={result.legacy_agency_id} className="mb-2">
                      <div className="font-medium">{result.legacy_agency_name || result.legacy_agency_id}</div>
                      {result.error && <div className="text-red-700">{result.error}</div>}
                      {(result.actions || []).map(action => <div key={action}>• {action}</div>)}
                      {(result.skipped || []).map(skip => <div key={skip} className="text-amber-700">• {skip}</div>)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => run(true)} disabled={busy || !preview?.agencies.length}>Önizle (kuru çalıştırma)</Button>
            <Button onClick={() => run(false)} disabled={busy || !plan || plan.some(result => result.error)} data-testid="legacy-migration-execute">
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Taşımayı uygula
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
