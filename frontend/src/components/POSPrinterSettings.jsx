import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select';
import { Printer, Plus, Trash2, RefreshCw, Send } from 'lucide-react';
import { alertDialog, confirmDialog } from '@/lib/dialogs';

// Operators register network (ESC/POS over TCP) or simulator printers and map
// each kitchen station to one — optionally per outlet. KOT auto-print resolves
// the (outlet_id, station) pair to the registered printer, so the same station
// (e.g. "hot_kitchen") can target a different physical printer in each outlet.

const EMPTY = {
  printer_id: '',
  name: '',
  driver: 'simulator',
  host: '',
  port: 9100,
  station: '',
  outlet_id: '',
  enabled: true,
  codepage: 'cp857',
};

const STATIONS = ['', 'hot_kitchen', 'cold_kitchen', 'bar', 'dessert'];

// Single-byte code pages. Turkish printers need cp857 (PC857) or cp1254
// (Windows-1254); UTF-8 prints Turkish characters as garbage.
const CODEPAGES = [
  { value: 'cp857', label: 'CP857 (PC857 Turkce)' },
  { value: 'cp1254', label: 'CP1254 (Windows Turkce)' },
  { value: 'cp850', label: 'CP850 (Cok dilli)' },
  { value: 'cp437', label: 'CP437 (Standart)' },
];

const POSPrinterSettings = () => {
  const [printers, setPrinters] = useState([]);
  const [outlets, setOutlets] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/pos/ext/print/printers');
      setPrinters(res.data.printers || []);
    } catch (err) {
      console.error('Yazicilar yuklenemedi:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOutlets = useCallback(async () => {
    try {
      const res = await axios.get('/pos/outlets');
      setOutlets(res.data?.outlets || []);
    } catch (err) {
      console.error('Outletler yuklenemedi:', err);
    }
  }, []);

  const outletName = useCallback((id) => {
    if (!id) return null;
    const o = outlets.find((x) => x.id === id);
    return o ? (o.name || o.id) : id;
  }, [outlets]);

  useEffect(() => { load(); loadOutlets(); }, [load, loadOutlets]);

  const setField = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

  const save = async () => {
    if (!form.printer_id.trim() || !form.name.trim()) {
      alertDialog({ message: 'Yazici kimligi ve adi zorunludur' });
      return;
    }
    if (form.driver === 'escpos_tcp' && !form.host.trim()) {
      alertDialog({ message: 'Ag yazicisi (escpos_tcp) icin host (IP) zorunludur' });
      return;
    }
    setSaving(true);
    try {
      await axios.post('/pos/ext/print/printers', {
        ...form,
        port: Number(form.port) || 9100,
        station: form.station || null,
        outlet_id: form.outlet_id || null,
        host: form.host || null,
        codepage: form.codepage || 'cp857',
      });
      setForm(EMPTY);
      await load();
    } catch (err) {
      alertDialog({ message: err.response?.data?.detail || 'Yazici kaydedilemedi' });
    } finally {
      setSaving(false);
    }
  };

  const remove = async (printerId) => {
    const ok = await confirmDialog({ message: `"${printerId}" yazicisini silmek istiyor musunuz?` });
    if (!ok) return;
    try {
      await axios.delete(`/pos/ext/print/printers/${printerId}`);
      await load();
    } catch (err) {
      alertDialog({ message: err.response?.data?.detail || 'Yazici silinemedi' });
    }
  };

  const test = async (printerId) => {
    setTestingId(printerId);
    try {
      const res = await axios.post(`/pos/ext/print/printers/${printerId}/test`);
      const status = res.data.status || 'unknown';
      const result = res.data.result || {};
      const reason = result.reason || result.error || '';
      alertDialog({
        message: status === 'sent'
          ? 'Test fisi gonderildi.'
          : `Test sonucu: ${status}. ${reason}`,
      });
    } catch (err) {
      alertDialog({ message: err.response?.data?.detail || 'Test gonderilemedi' });
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Add / edit form */}
      <Card className="lg:col-span-1">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="w-4 h-4" /> Yazici Ekle
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label>Yazici Kimligi</Label>
            <Input value={form.printer_id}
              onChange={(e) => setField('printer_id', e.target.value)}
              placeholder="orn. hot_kitchen"
              data-testid="printer-id" />
          </div>
          <div>
            <Label>Ad</Label>
            <Input value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              placeholder="orn. Sicak Mutfak Yazicisi"
              data-testid="printer-name" />
          </div>
          <div>
            <Label>Surucu</Label>
            <Select value={form.driver} onValueChange={(v) => setField('driver', v)}>
              <SelectTrigger data-testid="printer-driver"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="simulator">Simulator (test)</SelectItem>
                <SelectItem value="escpos_tcp">Ag yazicisi (ESC/POS TCP)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.driver === 'escpos_tcp' && (
            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-2">
                <Label>Host (IP)</Label>
                <Input value={form.host}
                  onChange={(e) => setField('host', e.target.value)}
                  placeholder="192.168.1.50"
                  data-testid="printer-host" />
              </div>
              <div>
                <Label>Port</Label>
                <Input type="number" value={form.port}
                  onChange={(e) => setField('port', e.target.value)}
                  data-testid="printer-port" />
              </div>
            </div>
          )}
          <div>
            <Label>Kod Sayfasi (Turkce karakter)</Label>
            <Select value={form.codepage || 'cp857'}
              onValueChange={(v) => setField('codepage', v)}>
              <SelectTrigger data-testid="printer-codepage"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CODEPAGES.map(c => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Istasyon (KOT yonlendirme)</Label>
            <Select value={form.station || '_none'}
              onValueChange={(v) => setField('station', v === '_none' ? '' : v)}>
              <SelectTrigger data-testid="printer-station"><SelectValue placeholder="Secin" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_none">Yok</SelectItem>
                {STATIONS.filter(Boolean).map(s => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Outlet (satis noktasi)</Label>
            <Select value={form.outlet_id || '_all'}
              onValueChange={(v) => setField('outlet_id', v === '_all' ? '' : v)}>
              <SelectTrigger data-testid="printer-outlet"><SelectValue placeholder="Secin" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">Tum outletler (varsayilan)</SelectItem>
                {outlets.map(o => (
                  <SelectItem key={o.id} value={o.id}>{o.name || o.id}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-500 mt-1">
              Bir outlet secerseniz, KOT yalnizca o outlet icin bu yaziciya gider.
              Bos birakirsaniz tum outletler icin paylasilan istasyon yazicisi olur.
            </p>
          </div>
          <Button className="w-full" onClick={save} disabled={saving} data-testid="printer-save">
            <Plus className="w-4 h-4 mr-2" />
            {saving ? 'Kaydediliyor...' : 'Kaydet'}
          </Button>
        </CardContent>
      </Card>

      {/* List */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Printer className="w-4 h-4" /> Kayitli Yazicilar
            </CardTitle>
            <Button variant="outline" size="sm" onClick={load} data-testid="printer-refresh">
              <RefreshCw className="w-4 h-4 mr-2" /> Yenile
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-gray-500">Yukleniyor...</div>
          ) : printers.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              Henuz yazici kaydi yok. Soldan ekleyin.
            </div>
          ) : (
            <div className="space-y-2">
              {printers.map(p => (
                <div key={p.printer_id}
                  className="flex items-center justify-between gap-2 p-3 border rounded"
                  data-testid={`printer-row-${p.printer_id}`}>
                  <div className="min-w-0">
                    <div className="font-medium flex items-center gap-2">
                      {p.name}
                      <Badge variant="outline" className="text-xs">{p.driver}</Badge>
                      {p.station && (
                        <Badge variant="secondary" className="text-xs">{p.station}</Badge>
                      )}
                      <Badge variant="outline" className="text-xs">
                        {p.outlet_id ? outletName(p.outlet_id) : 'tum outletler'}
                      </Badge>
                      {p.enabled === false && (
                        <Badge className="bg-gray-300 text-gray-700 text-xs">pasif</Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {p.printer_id}
                      {p.driver === 'escpos_tcp' && p.host ? ` • ${p.host}:${p.port}` : ''}
                      {p.codepage ? ` • ${p.codepage}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <Button variant="outline" size="sm"
                      onClick={() => test(p.printer_id)}
                      disabled={testingId === p.printer_id}
                      data-testid={`printer-test-${p.printer_id}`}>
                      <Send className="w-3.5 h-3.5 mr-1" />
                      {testingId === p.printer_id ? '...' : 'Test'}
                    </Button>
                    <Button variant="ghost" size="sm"
                      onClick={() => remove(p.printer_id)}
                      data-testid={`printer-delete-${p.printer_id}`}>
                      <Trash2 className="w-3.5 h-3.5 text-red-600" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default POSPrinterSettings;
