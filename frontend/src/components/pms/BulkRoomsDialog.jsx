import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Download, Lock, AlertTriangle } from 'lucide-react';

const MAX_ROOMS_PER_BATCH = 200;

const BulkRoomsDialog = ({ open, onClose, onRoomsCreated, user }) => {
  const { t } = useTranslation();
  const isSuperAdmin = user?.role === 'super_admin';

  const [bulkRoomTab, setBulkRoomTab] = useState('range');
  const [bulkRange, setBulkRange] = useState({ prefix: '', start_number: 101, end_number: 110, room_type: 'standard', floor: 1, capacity: 2, base_price: 150, view: '', bed_type: 'king', amenities: [] });
  const [bulkTemplate, setBulkTemplate] = useState({ prefix: '', start_number: 201, count: 5, room_type: 'deluxe', floor: 2, capacity: 2, base_price: 250, view: '', bed_type: 'king', amenities: [] });
  const [bulkCsvFile, setBulkCsvFile] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Live preview of room numbers that will be created (range tab)
  const rangePreview = useMemo(() => {
    const start = bulkRange.start_number;
    const end = bulkRange.end_number;
    if (!Number.isInteger(start) || !Number.isInteger(end)) return { count: 0, first: null, last: null, error: 'Başlangıç ve bitiş sayı olmalı.' };
    if (start < 1 || end < 1) return { count: 0, first: null, last: null, error: 'Oda numaraları 1\'den küçük olamaz.' };
    if (end < start) return { count: 0, first: null, last: null, error: 'Bitiş numarası başlangıçtan küçük olamaz.' };
    const count = end - start + 1;
    if (count > MAX_ROOMS_PER_BATCH) return { count, first: null, last: null, error: `Tek seferde en fazla ${MAX_ROOMS_PER_BATCH} oda oluşturabilirsiniz.` };
    const pfx = bulkRange.prefix || '';
    return { count, first: `${pfx}${start}`, last: `${pfx}${end}`, error: null };
  }, [bulkRange.start_number, bulkRange.end_number, bulkRange.prefix]);

  const templatePreview = useMemo(() => {
    const start = bulkTemplate.start_number;
    const count = bulkTemplate.count;
    if (!Number.isInteger(start) || !Number.isInteger(count)) return { count: 0, first: null, last: null, error: 'Başlangıç ve adet sayı olmalı.' };
    if (start < 1) return { count: 0, first: null, last: null, error: 'Başlangıç numarası 1\'den küçük olamaz.' };
    if (count <= 0) return { count: 0, first: null, last: null, error: 'Adet 1 veya daha fazla olmalı.' };
    if (count > MAX_ROOMS_PER_BATCH) return { count, first: null, last: null, error: `Tek seferde en fazla ${MAX_ROOMS_PER_BATCH} oda oluşturabilirsiniz.` };
    const pfx = bulkTemplate.prefix || '';
    return { count, first: `${pfx}${start}`, last: `${pfx}${start + count - 1}`, error: null };
  }, [bulkTemplate.start_number, bulkTemplate.count, bulkTemplate.prefix]);

  const resetConfirmOnChange = () => { if (confirmed) setConfirmed(false); };

  const handleClose = () => {
    setConfirmed(false);
    setSubmitting(false);
    onClose();
  };

  const handleBulkCreateRange = async (e) => {
    e.preventDefault();
    if (!isSuperAdmin) { toast.error('Oda oluşturma yetkisi yalnızca süper-admin kullanıcılara aittir.'); return; }
    if (rangePreview.error) { toast.error(rangePreview.error); return; }
    if (!confirmed) { toast.error('Lütfen oluşturulacak oda listesini onaylayın.'); return; }
    setSubmitting(true);
    try {
      const res = await axios.post('/pms/rooms/bulk/range', bulkRange);
      toast.success(`${res.data.created_count ?? res.data.created ?? rangePreview.count} oda oluşturuldu.`);
      handleClose();
      onRoomsCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Toplu oluşturma başarısız.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkCreateTemplate = async (e) => {
    e.preventDefault();
    if (!isSuperAdmin) { toast.error('Oda oluşturma yetkisi yalnızca süper-admin kullanıcılara aittir.'); return; }
    if (templatePreview.error) { toast.error(templatePreview.error); return; }
    if (!confirmed) { toast.error('Lütfen oluşturulacak oda listesini onaylayın.'); return; }
    setSubmitting(true);
    try {
      const res = await axios.post('/pms/rooms/bulk/template', bulkTemplate);
      toast.success(`${res.data.created_count ?? res.data.created ?? templatePreview.count} oda oluşturuldu.`);
      handleClose();
      onRoomsCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Toplu oluşturma başarısız.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkImportCsv = async (e) => {
    e.preventDefault();
    if (!isSuperAdmin) { toast.error('Oda oluşturma yetkisi yalnızca süper-admin kullanıcılara aittir.'); return; }
    if (!bulkCsvFile) return;
    if (!confirmed) { toast.error('CSV ile içe aktarma öncesi onayınız gerekli.'); return; }
    const formData = new FormData();
    formData.append('file', bulkCsvFile);
    setSubmitting(true);
    try {
      const res = await axios.post('/pms/rooms/import-csv', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`${res.data.created_count ?? res.data.created ?? ''} oda CSV'den içe aktarıldı.`);
      handleClose();
      onRoomsCreated?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'CSV içe aktarma başarısız.');
    } finally {
      setSubmitting(false);
    }
  };

  const downloadRoomsCsvTemplate = () => {
    const csv = 'room_number,room_type,floor,capacity,base_price,view,bed_type,amenities\n101,standard,1,2,150,city,king,wifi|minibar\n102,deluxe,1,3,250,sea,twin,wifi|minibar|balcony';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'rooms_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  const PreviewBox = ({ preview }) => (
    <div className={`rounded-md border p-3 text-sm ${preview.error ? 'border-red-300 bg-red-50 text-red-700' : 'border-amber-300 bg-amber-50 text-amber-900'}`}>
      <div className="flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          {preview.error ? (
            <div className="font-medium">{preview.error}</div>
          ) : (
            <>
              <div className="font-semibold">Oluşturulacak: {preview.count} oda</div>
              <div className="text-xs mt-1 opacity-80">Oda numaraları: <span className="font-mono">{preview.first}</span> … <span className="font-mono">{preview.last}</span></div>
              <div className="text-xs mt-1 opacity-75">Bu işlem geri alınamaz. Lütfen numaraları ve ayarları kontrol edin.</div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  const ConfirmCheckbox = ({ count, disabled }) => (
    <label className={`flex items-center gap-2 text-sm ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}>
      <input
        type="checkbox"
        checked={confirmed}
        disabled={disabled}
        onChange={(e) => setConfirmed(e.target.checked)}
        className="h-4 w-4"
      />
      <span>{count ? `${count} oda oluşturulmasını onaylıyorum` : 'Bu işlemi onaylıyorum'}</span>
    </label>
  );

  if (!isSuperAdmin) {
    return (
      <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Lock className="w-5 h-5" /> Yetki Gerekli</DialogTitle>
            <DialogDescription>Toplu oda oluşturma işlemi yalnızca süper-admin kullanıcılar tarafından yapılabilir.</DialogDescription>
          </DialogHeader>
          <div className="pt-2 flex justify-end">
            <Button variant="outline" onClick={handleClose}>{t('common.close', 'Kapat')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('pms.bulkAddRooms')}</DialogTitle>
          <DialogDescription>Range, template veya CSV ile toplu oda ekleme — işlem öncesi oluşturulacak odalar önizlenir ve onay gerekir.</DialogDescription>
        </DialogHeader>

        <Tabs value={bulkRoomTab} onValueChange={(v) => { setBulkRoomTab(v); setConfirmed(false); }} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="range">Range</TabsTrigger>
            <TabsTrigger value="template">Template</TabsTrigger>
            <TabsTrigger value="csv">CSV Import</TabsTrigger>
          </TabsList>

          <TabsContent value="range" className="pt-4">
            <form onSubmit={handleBulkCreateRange} className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Prefix</Label><Input value={bulkRange.prefix} onChange={(e) => { setBulkRange(p => ({...p, prefix: e.target.value})); resetConfirmOnChange(); }} placeholder="A" /></div>
                <div><Label>Start</Label><Input type="number" value={bulkRange.start_number} onChange={(e) => { setBulkRange(p => ({...p, start_number: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
                <div><Label>End</Label><Input type="number" value={bulkRange.end_number} onChange={(e) => { setBulkRange(p => ({...p, end_number: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>{t('booking.roomType')}</Label>
                  <Select value={bulkRange.room_type} onValueChange={(v) => { setBulkRange(p => ({...p, room_type: v})); resetConfirmOnChange(); }}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="standard">Standard</SelectItem>
                      <SelectItem value="deluxe">Deluxe</SelectItem>
                      <SelectItem value="suite">Suite</SelectItem>
                      <SelectItem value="presidential">Presidential</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Floor</Label><Input type="number" value={bulkRange.floor} onChange={(e) => { setBulkRange(p => ({...p, floor: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Capacity</Label><Input type="number" value={bulkRange.capacity} onChange={(e) => { setBulkRange(p => ({...p, capacity: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
                <div><Label>Base Price</Label><Input type="number" step="0.01" value={bulkRange.base_price} onChange={(e) => { setBulkRange(p => ({...p, base_price: parseFloat(e.target.value)})); resetConfirmOnChange(); }} /></div>
                <div><Label>View</Label><Input value={bulkRange.view} onChange={(e) => { setBulkRange(p => ({...p, view: e.target.value})); resetConfirmOnChange(); }} placeholder="sea/city" /></div>
              </div>

              <PreviewBox preview={rangePreview} />
              <ConfirmCheckbox count={rangePreview.count} disabled={!!rangePreview.error} />

              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={handleClose}>{t('common.cancel')}</Button>
                <Button type="submit" disabled={!confirmed || submitting || !!rangePreview.error}>{submitting ? 'Oluşturuluyor…' : t('common.create')}</Button>
              </div>
            </form>
          </TabsContent>

          <TabsContent value="template" className="pt-4">
            <form onSubmit={handleBulkCreateTemplate} className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Prefix</Label><Input value={bulkTemplate.prefix} onChange={(e) => { setBulkTemplate(p => ({...p, prefix: e.target.value})); resetConfirmOnChange(); }} placeholder="B" /></div>
                <div><Label>Start</Label><Input type="number" value={bulkTemplate.start_number} onChange={(e) => { setBulkTemplate(p => ({...p, start_number: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
                <div><Label>Count</Label><Input type="number" value={bulkTemplate.count} onChange={(e) => { setBulkTemplate(p => ({...p, count: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>{t('booking.roomType')}</Label>
                  <Select value={bulkTemplate.room_type} onValueChange={(v) => { setBulkTemplate(p => ({...p, room_type: v})); resetConfirmOnChange(); }}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="standard">Standard</SelectItem>
                      <SelectItem value="deluxe">Deluxe</SelectItem>
                      <SelectItem value="suite">Suite</SelectItem>
                      <SelectItem value="presidential">Presidential</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Floor</Label><Input type="number" value={bulkTemplate.floor} onChange={(e) => { setBulkTemplate(p => ({...p, floor: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Capacity</Label><Input type="number" value={bulkTemplate.capacity} onChange={(e) => { setBulkTemplate(p => ({...p, capacity: parseInt(e.target.value)})); resetConfirmOnChange(); }} /></div>
                <div><Label>Base Price</Label><Input type="number" step="0.01" value={bulkTemplate.base_price} onChange={(e) => { setBulkTemplate(p => ({...p, base_price: parseFloat(e.target.value)})); resetConfirmOnChange(); }} /></div>
                <div><Label>View</Label><Input value={bulkTemplate.view} onChange={(e) => { setBulkTemplate(p => ({...p, view: e.target.value})); resetConfirmOnChange(); }} placeholder="sea/city" /></div>
              </div>

              <PreviewBox preview={templatePreview} />
              <ConfirmCheckbox count={templatePreview.count} disabled={!!templatePreview.error} />

              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={handleClose}>{t('common.cancel')}</Button>
                <Button type="submit" disabled={!confirmed || submitting || !!templatePreview.error}>{submitting ? 'Oluşturuluyor…' : t('common.create')}</Button>
              </div>
            </form>
          </TabsContent>

          <TabsContent value="csv" className="pt-4">
            <form onSubmit={handleBulkImportCsv} className="space-y-4">
              <div className="text-sm text-gray-600">
                CSV columns: <span className="font-mono text-xs">room_number, room_type, floor, capacity, base_price, view, bed_type, amenities</span>
              </div>
              <Button type="button" variant="outline" onClick={downloadRoomsCsvTemplate}>
                <Download className="w-4 h-4 mr-2" />CSV Template
              </Button>
              <div><Label>CSV File</Label><Input type="file" accept=".csv,text/csv" onChange={(e) => { setBulkCsvFile(e.target.files?.[0] || null); resetConfirmOnChange(); }} /></div>

              {bulkCsvFile && (
                <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-semibold">Seçilen dosya: {bulkCsvFile.name}</div>
                      <div className="text-xs mt-1 opacity-80">Dosyadaki her satır bir oda olarak oluşturulacak. Mevcut oda numaralarıyla çakışanlar atlanır. İşlem geri alınamaz.</div>
                    </div>
                  </div>
                </div>
              )}
              <ConfirmCheckbox count={null} disabled={!bulkCsvFile} />

              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={handleClose}>{t('common.close')}</Button>
                <Button type="submit" disabled={!bulkCsvFile || !confirmed || submitting}>{submitting ? 'İçe aktarılıyor…' : 'Import'}</Button>
              </div>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};

export default BulkRoomsDialog;
