import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useCurrency } from '@/context/CurrencyContext';
import { formatAmount } from '@/lib/currency';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, Check, X, FileText, Plus } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { TabsContent } from '@/components/ui/tabs';

const HRAdvancesTab = ({ user, tenant }) => {
  const { t } = useTranslation();
  const { amount: fmtMoney } = useCurrency();
  const [advances, setAdvances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [answerDialog, setAnswerDialog] = useState({ open: false, req: null, type: null, note: '' });
  const [createDialog, setCreateDialog] = useState({ open: false, amount: '', reason: '', request_month: '' });

  const isHrManager = user?.role === 'admin' || user?.role === 'supervisor' || user?.role === 'finance';

  const fetchAdvances = useCallback(async () => {
    try {
      setLoading(true);
      const res = await axios.get('/hr/advances');
      setAdvances(res.data?.items || []);
    } catch (err) {
      console.error(err);
      toast.error('Avans talepleri yüklenirken hata oluştu.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAdvances();
  }, [fetchAdvances]);

  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/hr/advances', {
        staff_id: user.id,
        amount: parseFloat(createDialog.amount),
        currency: 'TRY',
        reason: createDialog.reason,
        request_month: createDialog.request_month
      });
      toast.success('Avans talebiniz başarıyla oluşturuldu.');
      setCreateDialog({ open: false, amount: '', reason: '', request_month: '' });
      fetchAdvances();
    } catch (err) {
      console.error(err);
      toast.error('Avans talebi oluşturulamadı. Lütfen bilgileri kontrol edin.');
    }
  };

  const handleAnswerSubmit = async () => {
    try {
      const { req, type, note } = answerDialog;
      await axios.post(`/hr/advances/${req.id}/decide`, {
        action: type,
        note: note || undefined,
      });
      toast.success('Talep yanıtı başarıyla iletildi.');
      setAnswerDialog({ open: false, req: null, type: null, note: '' });
      fetchAdvances();
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.detail || 'Talep yanıtı iletilemedi.');
    }
  };

  const getStatusBadge = (req) => {
    const statusMap = {
      'pending': { label: 'Bekliyor', color: 'bg-yellow-100 text-yellow-800' },
      'approved': { label: 'Onaylandı', color: 'bg-green-100 text-green-800' },
      'rejected': { label: 'Reddedildi', color: 'bg-red-100 text-red-800' },
    };
    const mapped = statusMap[req.status] || { label: req.status, color: 'bg-gray-100 text-gray-800' };
    return <Badge variant="outline" className={`font-medium ${mapped.color}`}>{mapped.label}</Badge>;
  };

  return (
    <TabsContent value="advances" className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold">Avans Talepleri</h2>
          <p className="text-sm text-gray-500">Personel avans taleplerini görüntüleyebilir ve yönetebilirsiniz.</p>
        </div>
        <div className="flex space-x-2">
          <Button variant="outline" onClick={fetchAdvances} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
          <Button onClick={() => setCreateDialog({ ...createDialog, open: true })}>
            <Plus className="w-4 h-4 mr-2" />
            Yeni Avans İste
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Yükleniyor...</div>
          ) : advances.length === 0 ? (
            <div className="p-8 text-center text-gray-500">Kayıtlı avans talebi bulunmuyor.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 font-medium text-gray-500">Tarih</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Bordro Ayı</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Personel</th>
                    <th className="px-4 py-3 font-medium text-gray-500 text-right">Tutar</th>
                    <th className="px-4 py-3 font-medium text-gray-500">Gerekçe</th>
                    <th className="px-4 py-3 font-medium text-gray-500 text-center">Durum</th>
                    {isHrManager && <th className="px-4 py-3 font-medium text-gray-500 text-right">İşlem</th>}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {advances.map(req => (
                    <tr key={req.id} className="hover:bg-gray-50/50">
                      <td className="px-4 py-3 whitespace-nowrap">
                        {new Date(req.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-medium text-blue-600">
                        {req.request_month}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{req.staff_name}</div>
                        <div className="text-xs text-gray-500">{req.staff_department}</div>
                      </td>
                      <td className="px-4 py-3 text-right font-medium">
                        {fmtMoney(req.amount, req.currency || 'TRY')}
                      </td>
                      <td className="px-4 py-3 max-w-xs truncate" title={req.reason}>
                        {req.reason}
                        {req.decision_note && <div className="text-xs text-red-500 mt-1">Not: {req.decision_note}</div>}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getStatusBadge(req)}
                      </td>
                      {isHrManager && (
                        <td className="px-4 py-3 text-right">
                          {req.status === 'pending' && (
                            <div className="flex items-center justify-end gap-2">
                              <Button size="sm" variant="outline" className="text-green-600 border-green-200 hover:bg-green-50"
                                onClick={() => setAnswerDialog({ open: true, req: req, type: 'approve', note: '' })}>
                                <Check className="w-4 h-4" />
                              </Button>
                              <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50"
                                onClick={() => setAnswerDialog({ open: true, req: req, type: 'reject', note: '' })}>
                                <X className="w-4 h-4" />
                              </Button>
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Answer Dialog */}
      <Dialog open={answerDialog.open} onOpenChange={(open) => !open && setAnswerDialog(prev => ({ ...prev, open: false }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {answerDialog.type === 'approve' ? 'Talebi Onayla' : 'Talebi Reddet'}
            </DialogTitle>
            <DialogDescription>
              <strong>{answerDialog.req?.staff_name}</strong> personelinin 
              <strong> {answerDialog.req?.request_month}</strong> bordrosundan kesilmek üzere istediği 
              <strong> {fmtMoney(answerDialog.req?.amount, answerDialog.req?.currency)}</strong> tutarındaki avans talebini
              {answerDialog.type === 'approve' ? ' KABUL' : ' RED'} etmek üzeresiniz.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Açıklama / Not {answerDialog.type === 'reject' && '(Zorunlu)'}
            </label>
            <Textarea
              placeholder={answerDialog.type === 'reject' ? 'Reddetme sebebinizi yazın...' : 'Personele iletilecek not (opsiyonel)...'}
              value={answerDialog.note}
              onChange={(e) => setAnswerDialog(prev => ({ ...prev, note: e.target.value }))}
              rows={3}
              required={answerDialog.type === 'reject'}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAnswerDialog(prev => ({ ...prev, open: false }))}>
              İptal
            </Button>
            <Button 
              variant={answerDialog.type === 'approve' ? 'default' : 'destructive'} 
              onClick={handleAnswerSubmit}
              disabled={answerDialog.type === 'reject' && !answerDialog.note.trim()}
            >
              {answerDialog.type === 'approve' ? 'Onayla' : 'Reddet'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Request Dialog */}
      <Dialog open={createDialog.open} onOpenChange={(open) => !open && setCreateDialog(prev => ({ ...prev, open: false }))}>
        <DialogContent>
          <form onSubmit={handleCreateSubmit}>
            <DialogHeader>
              <DialogTitle>Yeni Avans Talebi</DialogTitle>
              <DialogDescription>
                Bordronuzdan kesilmek üzere avans talebinde bulunun. Talebiniz yöneticinize onaya sunulacaktır.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tutar (TL)</label>
                <Input
                  type="number"
                  step="0.01"
                  min="1"
                  required
                  value={createDialog.amount}
                  onChange={e => setCreateDialog(prev => ({ ...prev, amount: e.target.value }))}
                  placeholder="Örn: 5000"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Bordro Ayı (YYYY-MM)</label>
                <Input
                  type="text"
                  required
                  pattern="\d{4}-\d{2}"
                  value={createDialog.request_month}
                  onChange={e => setCreateDialog(prev => ({ ...prev, request_month: e.target.value }))}
                  placeholder="Örn: 2026-09"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Gerekçe / Açıklama</label>
                <Textarea
                  required
                  rows={3}
                  value={createDialog.reason}
                  onChange={e => setCreateDialog(prev => ({ ...prev, reason: e.target.value }))}
                  placeholder="Avans talebinizin gerekçesini açıklayın..."
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateDialog(prev => ({ ...prev, open: false }))}>
                İptal
              </Button>
              <Button type="submit">Talebi Gönder</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </TabsContent>
  );
};

export default HRAdvancesTab;
